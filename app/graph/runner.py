from __future__ import annotations
import logging
from datetime import datetime, timezone
from typing import Any

from app.config import get_settings
from app.graph.graph import get_graph
from app.graph.state import ContentEngineState
from app.models import PipelineType, FailedItem, AssetRecord, TaskStatus
from app.task_store import task_store
from app.qa.health_checks import preflight_check, PIPELINE_SERVICES, PreflightError

logger = logging.getLogger(__name__)

PIPELINE_MAP = {
    "comment": PipelineType.text_only,
    "post":    PipelineType.text_image,
    "story":   PipelineType.text_image,
    "reels":   PipelineType.full_video,
}


def _resolve_pipeline(content_type: str) -> PipelineType:
    return PIPELINE_MAP.get(content_type, PipelineType.text_only)


def _build_initial_state(
    task_id: str,
    item_index: int,
    platform: str,
    content_type: str,
    language: str,
    quantity: int,
    description: str,
    pipeline_type: PipelineType,
    style_reference_image: str | None,
) -> ContentEngineState:
    return ContentEngineState(
        task_id=task_id,
        item_index=item_index,
        thread_id=f"{task_id}__item_{item_index}",
        platform=platform,
        content_type=content_type,
        language=language,
        quantity=quantity,
        description=description,
        pipeline_type=pipeline_type.value,
        style_reference_image=style_reference_image,
        visual_style_descriptor="",   
        generated_texts=[],
        generated_images=[],
        generated_videos=[],
        current_video_ref=None,
        completed_extends=0,
        all_video_refs=[],    # ← הוסף
        validation_results=[],
        retry_count=0,
        cost_accumulated=0.0,
        s3_manifest=None,
        status="pending",
        errors=[],
    )


async def _run_single_item(
    task_id: str,
    item_index: int,
    platform: str,
    content_type: str,
    language: str,
    quantity: int,
    description: str,
    pipeline_type: PipelineType,
    style_reference_image: str | None,
) -> dict[str, Any]:
    graph = get_graph()
    thread_id = f"{task_id}__item_{item_index}"

    initial_state = _build_initial_state(
        task_id=task_id,
        item_index=item_index,
        platform=platform,
        content_type=content_type,
        language=language,
        quantity=quantity,
        description=description,
        pipeline_type=pipeline_type,
        style_reference_image=style_reference_image,
    )

    config = {"configurable": {"thread_id": thread_id}}

    logger.info(
        "[%s] item_%d: starting pipeline=%s thread=%s",
        task_id, item_index, pipeline_type.value, thread_id,
    )

    result = await graph.ainvoke(initial_state, config=config)

    logger.info(
        "[%s] item_%d: pipeline completed status=%s cost=%.4f",
        task_id, item_index, result.get("status"), result.get("cost_accumulated", 0),
    )
    return result


async def run_batch(
    task_id: str,
    platform: str,
    content_type: str,
    language: str,
    quantity: int,
    description: str,
) -> None:
    pipeline_type = _resolve_pipeline(content_type)

    await task_store.update(
        task_id,
        status=TaskStatus.processing,
        pipeline_type=pipeline_type,
    )

    required_services = PIPELINE_SERVICES[pipeline_type.value]
    if get_settings().dry_run:
        logger.info("[%s] DRY_RUN: skipping pre-flight checks", task_id)
    else:
        try:
            await preflight_check(required_services)
            logger.info("[%s] Pre-flight OK: %s", task_id, required_services)
        except PreflightError as exc:
            await task_store.set_failed(task_id, str(exc))
            logger.error("[%s] Pre-flight FAILED: %s", task_id, exc)
            return

    failed_items: list[FailedItem] = []
    all_assets: list[AssetRecord] = []
    style_reference_image: str | None = None
    total_cost = 0.0
    total_checkpoint_savings = 0.0
    
    items_to_run = 1 if pipeline_type == PipelineType.text_only else quantity

    for i in range(items_to_run):
        logger.info("[%s] Starting item %d / %d", task_id, i, quantity - 1)
        try:
            result = await _run_single_item(
                task_id=task_id,
                item_index=i,
                platform=platform,
                content_type=content_type,
                language=language,
                quantity=quantity,
                description=description,
                pipeline_type=pipeline_type,
                style_reference_image=style_reference_image,
            )

            item_cost = result.get("cost_accumulated", 0.0)
            total_cost += item_cost
            await task_store.increment_cost(task_id, item_cost)

            if result.get("style_reference_image") and not style_reference_image:
                style_reference_image = result["style_reference_image"]
                logger.info("[%s] Style reference set from item_%d: %s", task_id, i, style_reference_image)

            for img in result.get("generated_images", []):
                all_assets.append(AssetRecord(
                    item_index=i,
                    asset_type="image",
                    s3_key=img.get("s3_key", ""),
                    file_format=img.get("format", "png"),
                    validation_passed=_item_passed_validation(result, i),
                    generation_cost_usd=item_cost,
                ))
            for vid in result.get("generated_videos", []):
                all_assets.append(AssetRecord(
                    item_index=i,
                    asset_type="video",
                    s3_key=vid.get("s3_key", ""),
                    file_format="mp4",
                    validation_passed=_item_passed_validation(result, i),
                    generation_cost_usd=item_cost,
                ))
            if result.get("generated_texts"):
                all_assets.append(AssetRecord(
                    item_index=i,
                    asset_type="text",
                    s3_key=f"tasks/{task_id}/{platform}/{content_type}/item_{i}/content.json",
                    file_format="json",
                    validation_passed=_item_passed_validation(result, i),
                    generation_cost_usd=item_cost,
                ))

            await task_store.update(task_id, items_completed=i + 1 - len(failed_items))

        except Exception as exc:
            logger.error("[%s] item_%d FAILED: %s", task_id, i, exc, exc_info=True)
            failed_items.append(FailedItem(
                index=i,
                stage=_infer_failure_stage(exc),
                error=str(exc),
                retryable=_is_retryable(exc),
            ))
            await task_store.add_error(task_id, f"item_{i}: {exc}")

    items_delivered = quantity - len(failed_items)
    final_status = (
        TaskStatus.completed if not failed_items
        else TaskStatus.partial if items_delivered > 0
        else TaskStatus.failed
    )

    manifest_key = await _write_manifest(
        task_id=task_id,
        platform=platform,
        content_type=content_type,
        language=language,
        quantity=quantity,
        items_delivered=items_delivered,
        failed_items=failed_items,
        assets=all_assets,
        total_cost=total_cost,
        checkpoint_savings=total_checkpoint_savings,
    )

    await task_store.update(
        task_id,
        status=final_status,
        items_completed=items_delivered,
        items_failed=len(failed_items),
        total_cost_usd=round(total_cost, 4),
        cost_saved_by_checkpoint=round(total_checkpoint_savings, 4),
        manifest_s3_key=manifest_key,
        completed_at=datetime.now(timezone.utc),
    )

    logger.info(
        "[%s] Batch complete: delivered=%d failed=%d cost=$%.4f status=%s",
        task_id, items_delivered, len(failed_items), total_cost, final_status,
    )


def _item_passed_validation(result: dict, item_index: int) -> bool:
    for vr in result.get("validation_results", []):
        if vr.get("item_id") == item_index:
            return vr.get("passed", False)
    return len(result.get("errors", [])) == 0


def _infer_failure_stage(exc: Exception) -> str:
    name = type(exc).__name__.lower()
    if "veo" in name or "video" in name:
        return "video_agent"
    if "image" in name or "gemini" in name:
        return "image_agent"
    if "claude" in name or "content" in name:
        return "content_agent"
    if "valid" in name:
        return "content_validator"
    return "unknown"


def _is_retryable(exc: Exception) -> bool:
    msg = str(exc).lower()
    return not any(s in msg for s in ["401", "403", "invalid api key", "quota exhausted", "400"])


async def _write_manifest(
    task_id: str,
    platform: str,
    content_type: str,
    language: str,
    quantity: int,
    items_delivered: int,
    failed_items: list[FailedItem],
    assets: list[AssetRecord],
    total_cost: float,
    checkpoint_savings: float,
) -> str:
    from app.services.s3_client import upload_json

    now = datetime.now(timezone.utc).isoformat()
    manifest = {
        "task_id": task_id,
        "status": "completed" if not failed_items else ("partial" if items_delivered > 0 else "failed"),
        "platform": platform,
        "content_type": content_type,
        "language": language,
        "quantity_requested": quantity,
        "quantity_delivered": items_delivered,
        "quantity_failed": len(failed_items),
        "total_cost_usd": round(total_cost, 4),
        "cost_saved_by_checkpoint": round(checkpoint_savings, 4),
        "created_at": now,
        "completed_at": now,
        "failed_items": [fi.model_dump() for fi in failed_items],
        "assets": [a.model_dump() for a in assets],
    }

   # ל:
    if content_type == "comment":
        root = "comments"
    elif content_type in ("post", "story"):
        root = "posts"
    else:
        root = "videos"

    s3_key = f"{root}/{task_id}/manifest.json"
    await upload_json(s3_key, manifest)
    logger.info("[%s] Manifest uploaded: %s", task_id, s3_key)
    return s3_key