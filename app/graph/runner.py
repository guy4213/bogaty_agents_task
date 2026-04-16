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

# ---------------------------------------------------------------------------
# Global semaphores — shared across all concurrent tasks
# Limits based on API rate limits:
#   text_only:  Claude 50 RPM       → 48
#   text_image: Imagen ~20 RPM      → 18
#   full_video: Veo 10 concurrent   → 8
# ---------------------------------------------------------------------------
import asyncio as _asyncio  # PARALLEL

_SEMAPHORES: dict[str, _asyncio.Semaphore] = {  # PARALLEL
    "text_only":  _asyncio.Semaphore(48),  # PARALLEL
    "text_image": _asyncio.Semaphore(18),  # PARALLEL
    "full_video": _asyncio.Semaphore(8),   # PARALLEL
}

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
    override_state: dict | None = None,   # ← חדש
) -> dict:
    graph  = get_graph()
    config = {"configurable": {"thread_id": f"{task_id}__item_{item_index}"}}

    initial_state = override_state or _build_initial_state(
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

    logger.info(
        "[%s] item_%d: starting pipeline=%s thread=%s",
        task_id, item_index, pipeline_type.value,
        f"{task_id}__item_{item_index}",
    )

    result = await graph.ainvoke(initial_state, config=config)
    return result

async def _run_item_with_semaphore(  # PARALLEL
    semaphore: _asyncio.Semaphore,  # PARALLEL
    task_id: str,  # PARALLEL
    item_index: int,  # PARALLEL
    platform: str,  # PARALLEL
    content_type: str,  # PARALLEL
    language: str,  # PARALLEL
    quantity: int,  # PARALLEL
    description: str,  # PARALLEL
    pipeline_type: PipelineType,  # PARALLEL
    style_reference_image: str | None,  # PARALLEL
    override_state: dict | None = None,  # PARALLEL
) -> dict:  # PARALLEL
    """Wraps _run_single_item with a semaphore to limit concurrency."""  # PARALLEL
    async with semaphore:  # PARALLEL
        return await _run_single_item(  # PARALLEL
            task_id=task_id,  # PARALLEL
            item_index=item_index,  # PARALLEL
            platform=platform,  # PARALLEL
            content_type=content_type,  # PARALLEL
            language=language,  # PARALLEL
            quantity=quantity,  # PARALLEL
            description=description,  # PARALLEL
            pipeline_type=pipeline_type,  # PARALLEL
            style_reference_image=style_reference_image,  # PARALLEL
            override_state=override_state,  # PARALLEL
        )  # PARALLEL

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
    all_assets:   list[AssetRecord] = []
    style_reference_image: str | None = None
    total_cost = 0.0
    total_checkpoint_savings = 0.0

    items_to_run = 1 if pipeline_type == PipelineType.text_only else quantity  # PARALLEL
    semaphore    = _SEMAPHORES[pipeline_type.value]  # PARALLEL

    # asyncio.Lock protects shared state updated from parallel coroutines
    _lock = _asyncio.Lock()  # PARALLEL

    # ------------------------------------------------------------------
    # Step 1: Run item_0 first (alone) to establish style_reference_image
    # ------------------------------------------------------------------
    async def _process_item(i: int, style_ref: str | None) -> tuple[int, dict | None]:  # PARALLEL
        """
        Runs a single item through the pipeline with Tier-3 checkpoint support.
        Returns (item_index, result_or_None).
        """  # PARALLEL
        from app.agents.video_agent import _PartialVideoError  # PARALLEL
        try:  # PARALLEL
            result = await _run_item_with_semaphore(  # PARALLEL
                semaphore=semaphore,  # PARALLEL
                task_id=task_id,  # PARALLEL
                item_index=i,  # PARALLEL
                platform=platform,  # PARALLEL
                content_type=content_type,  # PARALLEL
                language=language,  # PARALLEL
                quantity=quantity,  # PARALLEL
                description=description,  # PARALLEL
                pipeline_type=pipeline_type,  # PARALLEL
                style_reference_image=style_ref,  # PARALLEL
            )  # PARALLEL
            return i, result  # PARALLEL

        except Exception as exc:  # PARALLEL
            # Tier 3 checkpoint — partial video recovery
            if isinstance(exc, _PartialVideoError) and _is_retryable(exc):  # PARALLEL
                logger.info(  # PARALLEL
                    "[%s] item_%d _PartialVideoError — Tier 3 retry from extend=%d refs=%d",
                    task_id, i, exc.completed_extends, len(exc.all_video_refs),
                )  # PARALLEL
                try:  # PARALLEL
                    partial_state = _build_initial_state(  # PARALLEL
                        task_id=task_id,  # PARALLEL
                        item_index=i,  # PARALLEL
                        platform=platform,  # PARALLEL
                        content_type=content_type,  # PARALLEL
                        language=language,  # PARALLEL
                        quantity=quantity,  # PARALLEL
                        description=description,  # PARALLEL
                        pipeline_type=pipeline_type,  # PARALLEL
                        style_reference_image=style_ref,  # PARALLEL
                    )  # PARALLEL
                    partial_state["current_video_ref"] = exc.current_video_ref  # PARALLEL
                    partial_state["completed_extends"] = exc.completed_extends  # PARALLEL
                    partial_state["all_video_refs"]    = exc.all_video_refs  # PARALLEL
                    partial_state["generated_texts"]   = exc.generated_texts  # PARALLEL

                    result = await _run_item_with_semaphore(  # PARALLEL
                        semaphore=semaphore,  # PARALLEL
                        task_id=task_id,  # PARALLEL
                        item_index=i,  # PARALLEL
                        platform=platform,  # PARALLEL
                        content_type=content_type,  # PARALLEL
                        language=language,  # PARALLEL
                        quantity=quantity,  # PARALLEL
                        description=description,  # PARALLEL
                        pipeline_type=pipeline_type,  # PARALLEL
                        style_reference_image=style_ref,  # PARALLEL
                        override_state=partial_state,  # PARALLEL
                    )  # PARALLEL
                    logger.info("[%s] item_%d Tier 3 retry SUCCEEDED", task_id, i)  # PARALLEL
                    checkpoint_saving = exc.completed_extends * 0.20  # PARALLEL
                    async with _lock:  # PARALLEL
                        nonlocal total_checkpoint_savings  # PARALLEL
                        total_checkpoint_savings += checkpoint_saving  # PARALLEL
                    return i, result  # PARALLEL

                except Exception as retry_exc:  # PARALLEL
                    logger.error("[%s] item_%d Tier 3 retry FAILED: %s", task_id, i, retry_exc, exc_info=True)  # PARALLEL
                    async with _lock:  # PARALLEL
                        failed_items.append(FailedItem(  # PARALLEL
                            index=i,  # PARALLEL
                            stage=_infer_failure_stage(retry_exc),  # PARALLEL
                            error=str(retry_exc),  # PARALLEL
                            retryable=_is_retryable(retry_exc),  # PARALLEL
                        ))  # PARALLEL
                        await task_store.add_error(task_id, f"item_{i}: {retry_exc}")  # PARALLEL
                    return i, None  # PARALLEL
            else:  # PARALLEL
                logger.error("[%s] item_%d FAILED: %s", task_id, i, exc, exc_info=True)  # PARALLEL
                async with _lock:  # PARALLEL
                    failed_items.append(FailedItem(  # PARALLEL
                        index=i,  # PARALLEL
                        stage=_infer_failure_stage(exc),  # PARALLEL
                        error=str(exc),  # PARALLEL
                        retryable=_is_retryable(exc),  # PARALLEL
                    ))  # PARALLEL
                    await task_store.add_error(task_id, f"item_{i}: {exc}")  # PARALLEL
                return i, None  # PARALLEL

    async def _collect_result(i: int, result: dict) -> None:  # PARALLEL
        """Updates shared state from a completed item result (called under lock)."""  # PARALLEL
        nonlocal total_cost, style_reference_image  # PARALLEL
        item_cost = result.get("cost_accumulated", 0.0)  # PARALLEL
        total_cost += item_cost  # PARALLEL
        await task_store.increment_cost(task_id, item_cost)  # PARALLEL

        if result.get("style_reference_image") and not style_reference_image:  # PARALLEL
            style_reference_image = result["style_reference_image"]  # PARALLEL
            logger.info("[%s] Style reference set from item_%d: %s", task_id, i, style_reference_image)  # PARALLEL

        for img in result.get("generated_images", []):  # PARALLEL
            all_assets.append(AssetRecord(  # PARALLEL
                item_index=i,  # PARALLEL
                asset_type="image",  # PARALLEL
                s3_key=img.get("s3_key", ""),  # PARALLEL
                file_format=img.get("format", "png"),  # PARALLEL
                validation_passed=_item_passed_validation(result, i),  # PARALLEL
                generation_cost_usd=item_cost,  # PARALLEL
            ))  # PARALLEL
        for vid in result.get("generated_videos", []):  # PARALLEL
            all_assets.append(AssetRecord(  # PARALLEL
                item_index=i,  # PARALLEL
                asset_type="video",  # PARALLEL
                s3_key=vid.get("s3_key", ""),  # PARALLEL
                file_format="mp4",  # PARALLEL
                validation_passed=_item_passed_validation(result, i),  # PARALLEL
                generation_cost_usd=item_cost,  # PARALLEL
            ))  # PARALLEL
        if result.get("generated_texts"):  # PARALLEL
            root = "comments" if content_type == "comment" else ("posts" if content_type in ("post", "story") else "videos")  # PARALLEL
            all_assets.append(AssetRecord(  # PARALLEL
                item_index=i,  # PARALLEL
                asset_type="text",  # PARALLEL
                s3_key=f"{root}/{task_id}/{platform}/item_{i}/content.json",  # PARALLEL
                file_format="json",  # PARALLEL
                validation_passed=_item_passed_validation(result, i),  # PARALLEL
                generation_cost_usd=item_cost,  # PARALLEL
            ))  # PARALLEL

        await task_store.update(task_id, items_completed=items_to_run - len(failed_items))  # PARALLEL

    # ── Run item_0 first to establish style_reference_image ──
    logger.info("[%s] Starting item 0 / %d (anchor run)", task_id, items_to_run - 1)  # PARALLEL
    idx0, result0 = await _process_item(0, style_reference_image)  # PARALLEL
    if result0 is not None:  # PARALLEL
        async with _lock:  # PARALLEL
            await _collect_result(idx0, result0)  # PARALLEL

    # ── Run remaining items in parallel ──
    if items_to_run > 1:  # PARALLEL
        logger.info(  # PARALLEL
            "[%s] Starting items 1..%d in parallel (semaphore=%d)",
            task_id, items_to_run - 1, semaphore._value,
        )  # PARALLEL
        coros = [  # PARALLEL
            _process_item(i, style_reference_image)  # PARALLEL
            for i in range(1, items_to_run)  # PARALLEL
        ]  # PARALLEL
        results = await _asyncio.gather(*coros, return_exceptions=False)  # PARALLEL

        for idx, res in results:  # PARALLEL
            if res is not None:  # PARALLEL
                async with _lock:  # PARALLEL
                    await _collect_result(idx, res)  # PARALLEL

    # ------------------------------------------------------------------
    # manifest + final status
    # ------------------------------------------------------------------
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