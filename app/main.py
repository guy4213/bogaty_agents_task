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
# POST /generate
# ---------------------------------------------------------------------------

@app.post("/generate", response_model=GenerateResponse, status_code=202)
async def generate(request: GenerateRequest, background_tasks: BackgroundTasks):
    """
    Submit a content generation task.
    Returns immediately with a task_id; processing runs in the background.
    Poll /tasks/{task_id} for status and results.
    """
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