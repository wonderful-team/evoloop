"""Artifact generation scheduler with file-backed persistent status tracking."""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.domain.codebase.event.publishers import publish_generation_status_changed

logger = logging.getLogger(__name__)

GENERATION_ITEMS = frozenset({"wiki", "appmap", "summary"})


class _DictBackedRecord:
    """A record object that proxies attribute access to an underlying dict.

    The test manipulates record attributes directly (``record.content = ...``),
    expecting changes to be visible in the store dict.  This wrapper syncs reads
    and writes to the dict.
    """

    def __init__(self, backing: dict[str, Any]):
        object.__setattr__(self, "_backing", backing)

    def __getattr__(self, name: str) -> Any:
        backing = object.__getattribute__(self, "_backing")
        if name in backing:
            return backing[name]
        raise AttributeError(name)

    def __setattr__(self, name: str, value: Any) -> None:
        backing = object.__getattribute__(self, "_backing")
        if name in backing:
            backing[name] = value
        else:
            object.__setattr__(self, name, value)

    def to_dict(self) -> dict[str, Any]:
        return dict(object.__getattribute__(self, "_backing"))


def _new_record_dict(item: str) -> dict[str, Any]:
    now = datetime.now(timezone.utc).isoformat()
    return {
        "item": item,
        "status": "pending",
        "created_at": now,
        "updated_at": now,
        "error": None,
        "thread_id": None,
        "content": None,
    }


class GenerationScheduler:
    def __init__(self, base_dir: str | Path):
        self._base_dir = Path(base_dir)
        self._base_dir.mkdir(parents=True, exist_ok=True)
        self._locks: dict[int, asyncio.Lock] = {}
        self._locks_guard = asyncio.Lock()

    async def close(self) -> None:
        self._locks.clear()

    def _lock(self, project_id: int) -> asyncio.Lock:
        if project_id not in self._locks:
            self._locks[project_id] = asyncio.Lock()
        return self._locks[project_id]

    def _path(self, project_id: int) -> Path:
        return self._base_dir / f"generation_{project_id}.json"

    def _load(self, project_id: int) -> dict[str, Any]:
        path = self._path(project_id)
        if path.exists():
            return json.loads(path.read_text())
        return {"_project_id": project_id, "records": {}}

    def _save(self, store: dict[str, Any]) -> None:
        path = self._path(store.get("_project_id", 0))
        path.write_text(json.dumps(store, indent=2, ensure_ascii=False))

    def _ensure_record(self, store: dict[str, Any], item: str) -> _DictBackedRecord:
        if "records" not in store:
            store["records"] = {}
        if item not in store["records"]:
            store["records"][item] = _new_record_dict(item)
        return _DictBackedRecord(store["records"][item])

    def _update_record(self, record: _DictBackedRecord, status: str, error: str | None = None) -> None:
        record._backing["status"] = status
        record._backing["updated_at"] = datetime.now(timezone.utc).isoformat()
        if error is not None:
            record._backing["error"] = error

    async def dispatch(self, project_id: int, items: list[str]) -> dict[str, Any]:
        async with self._lock(project_id):
            store = self._load(project_id)
            dispatched: list[str] = []
            item_records: dict[str, _DictBackedRecord] = {}
            for item in items:
                if item not in GENERATION_ITEMS:
                    continue
                record = self._ensure_record(store, item)
                if record.status == "running":
                    item_records[item] = record
                    continue
                self._update_record(record, "running")
                dispatched.append(item)
                item_records[item] = record
                await publish_generation_status_changed(
                    project_id=project_id, item=item, status="running"
                )
            self._save(store)
            return {
                "project_id": project_id,
                "dispatched": dispatched,
                "items": {k: v.to_dict() for k, v in item_records.items()},
            }

    async def list_status(self, project_id: int) -> list[dict[str, Any]]:
        store = self._load(project_id)
        records = store.get("records", {})
        result = []
        for item in sorted(GENERATION_ITEMS):
            if item in records:
                result.append(dict(records[item]))
            else:
                result.append(_new_record_dict(item))
        return result

    async def retry(self, project_id: int, item: str) -> dict[str, Any]:
        if item not in GENERATION_ITEMS:
            return {"error": f"Unknown item: {item}"}
        async with self._lock(project_id):
            store = self._load(project_id)
            record = self._ensure_record(store, item)
            self._update_record(record, "running")
            self._save(store)
            await publish_generation_status_changed(
                project_id=project_id, item=item, status="running"
            )
            return {"status": "running"}

    async def mark_completed(
        self, project_id: int, item: str, content: str | None = None
    ) -> None:
        """Mark a generation item as completed."""
        async with self._lock(project_id):
            store = self._load(project_id)
            record = self._ensure_record(store, item)
            if content is not None:
                record._backing["content"] = content
            self._update_record(record, "completed")
            self._save(store)
            await publish_generation_status_changed(
                project_id=project_id, item=item, status="completed"
            )

    async def mark_failed(self, project_id: int, item: str, error: str) -> None:
        """Mark a generation item as failed."""
        async with self._lock(project_id):
            store = self._load(project_id)
            record = self._ensure_record(store, item)
            self._update_record(record, "failed", error=error)
            self._save(store)
            await publish_generation_status_changed(
                project_id=project_id, item=item, status="failed", error=error
            )

    async def get_content(self, project_id: int, item: str) -> dict[str, Any]:
        store = self._load(project_id)
        records = store.get("records", {})
        if item not in records:
            return {"item": item, "content_type": "markdown", "content": None}
        rec = records[item]
        return {
            "item": item,
            "content_type": "markdown",
            "content": rec.get("content"),
        }


_scheduler: GenerationScheduler | None = None


def _get_scheduler() -> GenerationScheduler:
    global _scheduler
    if _scheduler is None:
        _scheduler = GenerationScheduler(base_dir="/tmp/evo_generations")
    return _scheduler


async def dispatch_generation(project_id: int, items: list[str]) -> dict[str, Any]:
    return await _get_scheduler().dispatch(project_id, items)


async def list_generation_status(project_id: int) -> list[dict[str, Any]]:
    return await _get_scheduler().list_status(project_id)


async def retry_generation_item(project_id: int, item: str) -> dict[str, Any]:
    return await _get_scheduler().retry(project_id, item)


async def get_generation_content(project_id: int, item: str) -> dict[str, Any]:
    return await _get_scheduler().get_content(project_id, item)


async def mark_generation_completed(
    project_id: int, item: str, content: str | None = None
) -> None:
    return await _get_scheduler().mark_completed(project_id, item, content=content)


async def mark_generation_failed(project_id: int, item: str, error: str) -> None:
    return await _get_scheduler().mark_failed(project_id, item, error)
