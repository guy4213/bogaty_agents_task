from __future__ import annotations
import asyncio
import logging
import sys
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timezone

from fastapi import FastAPI, BackgroundTasks, HTTPException, Path
from fastapi.responses import JSONResponse

from app.config import get_settings
from app.graph.runner import run_batch
from app.graph.graph import get_graph  # pre-builds graph at startup
from app.models import (
    GenerateRequest,
    GenerateResponse,
    TaskStatusResponse,
    HealthResponse,
    ServiceHealth,
    TaskStatus,
)
from app.task_store import task_store
from app.qa.health_checks import check_all_services
from app.qa.circuit_breaker import all_breakers

# ---------------------------------------------------------------------------
# Logging setup
# ---------------------------------------------------------------------------

def _configure_logging() -> None:
    cfg = get_settings()
    logging.basicConfig(
        level=getattr(logging, cfg.log_level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
        stream=sys.stdout,
    )
    # Quiet noisy libraries
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logging.getLogger("botocore").setLevel(logging.WARNING)
    logging.getLogger("boto3").setLevel(logging.WARNING)


logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Lifespan — startup / shutdown
# ---------------------------------------------------------------------------

@asynccontextmanager
async def lifespan(app: FastAPI):
    _configure_logging()
    cfg = get_settings()

    # Pre-build LangGraph (warms up MemorySaver and graph compilation)
    get_graph()
    logger.info("LangGraph compiled and ready")

    # Optional LangSmith tracing
    if cfg.langsmith_tracing and cfg.langsmith_api_key:
        import os
        os.environ["LANGCHAIN_TRACING_V2"] = "true"
        os.environ["LANGCHAIN_API_KEY"] = cfg.langsmith_api_key
        logger.info("LangSmith tracing enabled")

    logger.info("Content Engine API started — model=%s", cfg.claude_model)
    yield
    logger.info("Content Engine API shutting down")


# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------

app = FastAPI(
    title="Content Engine",
    description="Autonomous multi-modal content generation for social platforms",
    version="1.0.0-mvp",
    lifespan=lifespan,
)


# ---------------------------------------------------------------------------
# Input validation limits — based on API rate limits and system capacity
# ---------------------------------------------------------------------------
MAX_QUANTITY: dict[str, int] = {  # PARALLEL
    "comment": 200,   # Single Claude batch call — high capacity  # PARALLEL
    "post":    50,    # Claude + Imagen per item  # PARALLEL
    "story":   50,    # Claude + Imagen per item  # PARALLEL
    "reels":   50,    # Claude + Imagen + 4×Veo per item  # PARALLEL
}  # PARALLEL

# ---------------------------------------------------------------------------
# POST /generate
# ---------------------------------------------------------------------------

@app.post("/generate", response_model=GenerateResponse, status_code=202)
async def generate(request: GenerateRequest, background_tasks: BackgroundTasks):
    """
    Submit a content generation task.
    Returns immediately with a task_id; processing runs in the background.
    Poll /tasks/{task_id} for status and results.
    """
    # Validate quantity against system limits
    max_qty = MAX_QUANTITY.get(request.content_type.value, 50)  # PARALLEL
    if request.quantity < 1:  # PARALLEL
        raise HTTPException(  # PARALLEL
            status_code=422,  # PARALLEL
            detail=f"quantity must be at least 1."  # PARALLEL
        )  # PARALLEL
    if request.quantity > max_qty:  # PARALLEL
        raise HTTPException(  # PARALLEL
            status_code=422,  # PARALLEL
            detail=(  # PARALLEL
                f"quantity={request.quantity} exceeds maximum for "  # PARALLEL
                f"content_type='{request.content_type.value}' (max={max_qty}). "  # PARALLEL
                f"Submit multiple requests to generate more."  # PARALLEL
            )  # PARALLEL
        )  # PARALLEL

    record = await task_store.create(
        platform=request.platform.value,
        content_type=request.content_type.value,
        language=request.language.value,
        quantity=request.quantity,
        description=request.description,
    )

    logger.info(
        "Task created: id=%s platform=%s type=%s lang=%s qty=%d",
        record.task_id,
        record.platform,
        record.content_type,
        record.language,
        record.quantity,
    )

    # Fire-and-forget in background
    background_tasks.add_task(
        run_batch,
        task_id=record.task_id,
        platform=record.platform,
        content_type=record.content_type,
        language=record.language,
        quantity=record.quantity,
        description=record.description,
    )

    return GenerateResponse(
        task_id=record.task_id,
        status=TaskStatus.pending,
        message=f"Task accepted. Poll /tasks/{record.task_id} for status.",
    )


# ---------------------------------------------------------------------------
# GET /tasks/{task_id}
# ---------------------------------------------------------------------------

@app.get("/tasks/{task_id}", response_model=TaskStatusResponse)
async def get_task(task_id: str = Path(..., description="Task UUID")):
    """Retrieve the current status and results of a generation task."""
    record = await task_store.get(task_id)
    if record is None:
        raise HTTPException(status_code=404, detail=f"Task '{task_id}' not found")

    presigned = None
    if record.manifest_s3_key:
        try:
            from app.services.s3_client import presigned_url
            presigned = await presigned_url(record.manifest_s3_key)
        except Exception as exc:
            logger.warning("Could not generate presigned URL for %s: %s", record.manifest_s3_key, exc)

    return TaskStatusResponse(
        task_id=record.task_id,
        status=record.status,
        platform=record.platform,
        content_type=record.content_type,
        quantity_requested=record.quantity,
        quantity_delivered=record.items_completed,
        quantity_failed=record.items_failed,
        total_cost_usd=record.total_cost_usd,
        cost_saved_by_checkpoint=record.cost_saved_by_checkpoint,
        manifest_s3_key=record.manifest_s3_key,
        presigned_manifest_url=presigned,
        errors=record.errors,
    )


# ---------------------------------------------------------------------------
# GET /tasks  (list all — useful for dev/demo)
# ---------------------------------------------------------------------------

@app.get("/tasks")
async def list_tasks():
    """List all tasks in the in-memory store (dev/demo use)."""
    records = task_store.list_all()
    return [
        {
            "task_id": r.task_id,
            "status": r.status,
            "platform": r.platform,
            "content_type": r.content_type,
            "quantity": r.quantity,
            "items_completed": r.items_completed,
            "items_failed": r.items_failed,
            "total_cost_usd": r.total_cost_usd,
            "created_at": r.created_at.isoformat(),
        }
        for r in records
    ]


# ---------------------------------------------------------------------------
# GET /health
# ---------------------------------------------------------------------------

@app.get("/health", response_model=HealthResponse)
async def health():
    """
    Infrastructure health check.
    Pings Claude, Gemini, and S3 and reports circuit breaker states.
    Used by the Orchestrator pre-flight check and external monitoring.
    """
    services = await check_all_services()

    # Merge in any breakers that haven't been pinged yet
    breakers = all_breakers()
    pinged_names = {s.service for s in services}
    for svc_name, breaker in breakers.items():
        if svc_name not in pinged_names:
            services.append(
                ServiceHealth(
                    service=svc_name,
                    status="unknown",
                    circuit_state=breaker.state.value,
                )
            )

    overall = "healthy"
    for s in services:
        if s.status == "down":
            overall = "down"
            break
        if s.status == "degraded":
            overall = "degraded"

    return HealthResponse(
        overall=overall,
        services=services,
        timestamp=datetime.now(timezone.utc).isoformat(),
    )


# ---------------------------------------------------------------------------
# GET /  (root — liveness probe)
# ---------------------------------------------------------------------------

@app.get("/")
async def root():
    return {"status": "ok", "service": "content-engine", "version": "1.0.0-mvp"}

# ---------------------------------------------------------------------------
# GET /tasks/{task_id}/content  — list all assets with readable content
# ---------------------------------------------------------------------------

@app.get("/tasks/{task_id}/content")
async def get_task_content(task_id: str = Path(...)):
    """
    Returns all generated content for a task.
    In dry-run mode reads from local filesystem.
    In production returns presigned S3 URLs for every asset.
    """
    record = await task_store.get(task_id)
    if record is None:
        raise HTTPException(status_code=404, detail=f"Task '{task_id}' not found")

    if record.status.value == "pending":
        return {"task_id": task_id, "status": "pending", "message": "Task not started yet"}

    if record.status.value == "processing":
        return {"task_id": task_id, "status": "processing", "message": "Still running, try again shortly"}

    if not record.manifest_s3_key:
        raise HTTPException(status_code=404, detail="Manifest not yet available")

    # Read manifest
    manifest = await _read_manifest(record.manifest_s3_key)
    if not manifest:
        raise HTTPException(status_code=404, detail="Manifest file not found")

    # Build response with inline text content + URLs for binary assets
    assets_out = []
    for asset in manifest.get("assets", []):
        s3_key = asset.get("s3_key", "")
        file_format = asset.get("file_format", "")
        asset_type = asset.get("asset_type", "")

        entry = {
            "item_index": asset.get("item_index"),
            "asset_type": asset_type,
            "file_format": file_format,
            "s3_key": s3_key,
            "validation_passed": asset.get("validation_passed"),
        }

        # For text/json assets — inline the actual content
        if file_format in ("json", "txt") or asset_type in ("text", "caption"):
            content = await _read_asset_text(s3_key)
            if content:
                try:
                    import json as _json
                    entry["content"] = _json.loads(content)
                except Exception:
                    entry["content"] = content

        # For binary assets — generate a download URL
        else:
            try:
                from app.services.s3_client import presigned_url
                entry["download_url"] = await presigned_url(s3_key, expiry_sec=3600)
            except Exception:
                entry["download_url"] = None

        assets_out.append(entry)

    return {
        "task_id": task_id,
        "status": manifest.get("status"),
        "platform": manifest.get("platform"),
        "content_type": manifest.get("content_type"),
        "language": manifest.get("language"),
        "quantity_requested": manifest.get("quantity_requested"),
        "quantity_delivered": manifest.get("quantity_delivered"),
        "total_cost_usd": manifest.get("total_cost_usd"),
        "assets": assets_out,
    }


# ---------------------------------------------------------------------------
# GET /tasks/{task_id}/content/{item_index}  — single item detail
# ---------------------------------------------------------------------------

@app.get("/tasks/{task_id}/content/{item_index}")
async def get_item_content(
    task_id: str = Path(...),
    item_index: int = Path(...),
):
    """
    Returns all assets for a single item in the batch.
    Text content is returned inline. Images/video get presigned download URLs.
    """
    record = await task_store.get(task_id)
    if record is None:
        raise HTTPException(status_code=404, detail=f"Task '{task_id}' not found")

    if not record.manifest_s3_key:
        raise HTTPException(status_code=404, detail="Manifest not yet available")

    manifest = await _read_manifest(record.manifest_s3_key)
    if not manifest:
        raise HTTPException(status_code=404, detail="Manifest file not found")

    # Filter assets for this item
    item_assets = [a for a in manifest.get("assets", []) if a.get("item_index") == item_index]
    if not item_assets:
        raise HTTPException(status_code=404, detail=f"No assets found for item {item_index}")

    result = {"task_id": task_id, "item_index": item_index, "files": {}}

    for asset in item_assets:
        s3_key = asset.get("s3_key", "")
        file_format = asset.get("file_format", "")
        asset_type = asset.get("asset_type", "")
        filename = s3_key.split("/")[-1] if s3_key else "unknown"

        if file_format in ("json", "txt") or asset_type in ("text", "caption"):
            content = await _read_asset_text(s3_key)
            if content:
                try:
                    import json as _json
                    result["files"][filename] = _json.loads(content)
                except Exception:
                    result["files"][filename] = content
        else:
            try:
                from app.services.s3_client import presigned_url
                result["files"][filename] = await presigned_url(s3_key, expiry_sec=3600)
            except Exception:
                result["files"][filename] = None

    return result


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def _read_manifest(manifest_s3_key: str) -> dict | None:
    """Read manifest.json from S3 or local filesystem (dry run)."""
    import json as _json
    from app.config import get_settings

    if get_settings().dry_run:
        from app.mocks.mock_clients import _LOCAL_S3_ROOT
        path = _LOCAL_S3_ROOT / manifest_s3_key
        if not path.exists():
            return None
        return _json.loads(path.read_text(encoding="utf-8"))

    try:
        from app.services.s3_client import _get_client
        cfg = get_settings()
        import asyncio
        loop = asyncio.get_event_loop()
        s3 = _get_client()
        resp = await loop.run_in_executor(
            None,
            lambda: s3.get_object(Bucket=cfg.s3_bucket_name, Key=manifest_s3_key),
        )
        return _json.loads(resp["Body"].read().decode("utf-8"))
    except Exception:
        return None


async def _read_asset_text(s3_key: str) -> str | None:
    """Read a text/json asset as string from S3 or local filesystem."""
    from app.config import get_settings

    if get_settings().dry_run:
        from app.mocks.mock_clients import _LOCAL_S3_ROOT
        path = _LOCAL_S3_ROOT / s3_key
        if not path.exists():
            return None
        return path.read_text(encoding="utf-8")

    try:
        from app.services.s3_client import _get_client
        cfg = get_settings()
        import asyncio
        loop = asyncio.get_event_loop()
        s3 = _get_client()
        resp = await loop.run_in_executor(
            None,
            lambda: s3.get_object(Bucket=cfg.s3_bucket_name, Key=s3_key),
        )
        return resp["Body"].read().decode("utf-8")
    except Exception:
        return None