"""DynamicAppTriage fire-and-forget 契约测试。

背景（2026-09-21 事故）：scan 循环曾用 `delay(batch).get(timeout=120)` 同步
等待，而网关分诊单批实测 97-136s——超预算批次被误报 failed，且 processed
集合由调用方写，导致丢结果的 App 每周期重审、串行等待引发超时连锁。
修复 = 控制权倒置：worker 任务自己落缓存（persist_triage_results），
调用方只入队。本文件锁定两侧契约。
"""

import types

from app.core.environment.constants import DYNAMIC_APP_TRIAGE_BATCH_SIZE
from app.core.environment.explorers import dynamic_apps as da
from app.core.environment.explorers import tasks as triage_tasks


class _Pipe:
    def __init__(self):
        self.ops = []

    def sadd(self, key, member):
        self.ops.append(("sadd", key, member))

    def hset(self, key, field, value):
        self.ops.append(("hset", key, field, value))

    async def execute(self):
        return True


class _Cache:
    def __init__(self, members=None):
        self._members = members or {}
        self.pipe = _Pipe()

    async def smembers(self, key):
        return self._members.get(key, set())

    def pipeline(self):
        return self.pipe


async def test_sync_dynamic_apps_enqueues_without_waiting(monkeypatch):
    enqueued = []
    fake_task = types.SimpleNamespace(
        delay=lambda batch, platform: enqueued.append((tuple(batch), platform))
    )
    monkeypatch.setattr(
        "app.core.environment.explorers.tasks.triage_app_batch", fake_task
    )
    monkeypatch.setattr(da, "cache", _Cache({"system:processed_apps:macos": set()}))

    apps = [f"app{i}" for i in range(7)]
    await da.DynamicAppTriage().sync_dynamic_apps(macos_apps=apps)

    flat = [a for batch, _ in enqueued for a in batch]
    assert sorted(flat) == sorted(apps)
    assert all(p == "macos" for _, p in enqueued)
    expected_batches = (len(apps) + DYNAMIC_APP_TRIAGE_BATCH_SIZE - 1) // DYNAMIC_APP_TRIAGE_BATCH_SIZE
    assert len(enqueued) == expected_batches


async def test_persist_triage_results_marks_processed_and_dynamic(monkeypatch):
    cache = _Cache()
    monkeypatch.setattr(triage_tasks, "cache", cache)

    results = {
        "AppA": {"is_dynamic": True, "reason": "scrolling list"},
        "AppB": {"is_dynamic": False, "reason": "static UI"},
    }
    await triage_tasks.persist_triage_results("macos", results)

    ops = cache.pipe.ops
    # 处理过的 App 无论动/静都必须进 processed（否则每周期重审）
    assert ("sadd", "system:processed_apps:macos", "AppA") in ops
    assert ("sadd", "system:processed_apps:macos", "AppB") in ops
    # 仅动态 App 进 dynamic 集合并留理由
    assert ("sadd", "system:dynamic_apps:macos", "AppA") in ops
    assert ("hset", "system:app_categorization:macos", "AppA", "scrolling list") in ops
    assert ("sadd", "system:dynamic_apps:macos", "AppB") not in ops


async def test_empty_results_persist_nothing(monkeypatch):
    cache = _Cache()
    monkeypatch.setattr(triage_tasks, "cache", cache)
    await triage_tasks.persist_triage_results("macos", {})
    assert cache.pipe.ops == []
