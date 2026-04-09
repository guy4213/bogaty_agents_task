from __future__ import annotations
import asyncio
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any
import uuid

from app.models import TaskStatus, PipelineType


@dataclass
class TaskRecord:
    task_id: str
    platform: str
    content_type: str
    language: str
    quantity: int
    description: str
    pipeline_type: PipelineType | None = None
    status: TaskStatus = TaskStatus.pending

    # Counters
    items_completed: int = 0
    items_failed: int = 0

    # Cost tracking
    total_cost_usd: float = 0.0
    cost_saved_by_checkpoint: float = 0.0

    # Storage
    manifest_s3_key: str | None = None
    presigned_manifest_url: str | None = None

    # Error log
    errors: list[str] = field(default_factory=list)

    # Timestamps
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    completed_at: datetime | None = None


class TaskStore:
    """Thread-safe in-memory task registry. Swap repository layer for PostgreSQL post-MVP."""

    def __init__(self) -> None:
        self._tasks: dict[str, TaskRecord] = {}
        self._lock = asyncio.Lock()

    async def create(
        self,
        platform: str,
        content_type: str,
        language: str,
        quantity: int,
        description: str,
    ) -> TaskRecord:
        task_id = str(uuid.uuid4())
        record = TaskRecord(
            task_id=task_id,
            platform=platform,
            content_type=content_type,
            language=language,
            quantity=quantity,
            description=description,
        )
        async with self._lock:
            self._tasks[task_id] = record
        return record

    async def get(self, task_id: str) -> TaskRecord | None:
        async with self._lock:
            return self._tasks.get(task_id)

    async def update(self, task_id: str, **kwargs: Any) -> TaskRecord | None:
        async with self._lock:
            record = self._tasks.get(task_id)
            if record is None:
                return None
            for key, value in kwargs.items():
                if hasattr(record, key):
                    setattr(record, key, value)
            return record

    async def set_completed(self, task_id: str) -> None:
        async with self._lock:
            record = self._tasks.get(task_id)
            if record:
                record.status = TaskStatus.completed
                record.completed_at = datetime.now(timezone.utc)

    async def set_failed(self, task_id: str, error: str) -> None:
        async with self._lock:
            record = self._tasks.get(task_id)
            if record:
                record.status = TaskStatus.failed
                record.errors.append(error)
                record.completed_at = datetime.now(timezone.utc)

    async def add_error(self, task_id: str, error: str) -> None:
        async with self._lock:
            record = self._tasks.get(task_id)
            if record:
                record.errors.append(error)

    async def increment_cost(self, task_id: str, amount: float) -> None:
        async with self._lock:
            record = self._tasks.get(task_id)
            if record:
                record.total_cost_usd = round(record.total_cost_usd + amount, 6)

    async def add_checkpoint_saving(self, task_id: str, amount: float) -> None:
        async with self._lock:
            record = self._tasks.get(task_id)
            if record:
                record.cost_saved_by_checkpoint = round(
                    record.cost_saved_by_checkpoint + amount, 6
                )

    def list_all(self) -> list[TaskRecord]:
        return list(self._tasks.values())


# Singleton — shared across the app
task_store = TaskStore()