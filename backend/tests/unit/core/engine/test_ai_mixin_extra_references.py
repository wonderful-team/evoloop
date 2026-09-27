"""AI 消息媒体引用直传链路契约测试。

锁定（此前真实踩坑）：
- image/video 工具 stash 的引用经 consume_pending_media_refs 一次性消费；
- ai_mixin.handle_ai_message 将 extra_references 与正文提取结果合并去重后落库；
- SSE dispatch 块（persist 分支）必须携带合并后的 references，
  否则前端实时渲染丢失图片（刷新才可见的老 bug）。
"""

from types import SimpleNamespace

import pytest

from app.core.engine.message.handler.ai_mixin import AiMessageMixin
from app.core.engine.message.media_refs import consume_pending_media_refs

PUBLIC_URL_A = "https://evoloop.cn/upload/chat_img/20260914/a.png"
PUBLIC_URL_B = "https://evoloop.cn/upload/chat_img/20260914/b.png"

STASH_REF = {
    "id": "ref-id-1",
    "type": "image",
    "target_id": PUBLIC_URL_A,
    "target_name": "generated image",
    "meta_data": {"source_path": PUBLIC_URL_A},
}


def _make_handler(persisted: dict):
    """最小化 AiMessageMixin 宿主：策略类走真实实现，repo/dedup/dispatch 打桩。"""

    class _Repo:
        async def get_last_message_id(self):
            return "parent-1"

        async def persist(self, **kwargs):
            persisted.update(kwargs)
            return "msg-1", 7

    class _Dedup:
        def is_duplicate(self, *a, **k):
            return False

    class _Handler(AiMessageMixin):
        def __init__(self):
            self._repository = _Repo()
            self._deduplicator = _Dedup()
            self.last_persisted_message_id = None
            self.last_persisted_sequence = 0
            self.dispatched: list[dict] = []

        def _get_device_attribution(self):
            return "dev-key", "Dev Name"

        async def _dispatch_block(self, **kwargs):
            self.dispatched.append(kwargs)

    return _Handler()


@pytest.fixture
def fake_extractor(monkeypatch):
    """控制 attachment_extractor 的提取结果。"""

    def _set(refs: list[dict]):
        from app.core.engine.message import extractor as extractor_mod

        def _extract(content=None, **kwargs):  # noqa: ARG001
            return list(refs)

        monkeypatch.setattr(
            extractor_mod.attachment_extractor,
            "extract_from_ai_response",
            _extract,
        )

    return _set


@pytest.mark.asyncio
async def test_extra_references_merged_into_persist(fake_extractor):
    persisted: dict = {}
    handler = _make_handler(persisted)
    fake_extractor([])  # 正文无链接 → 全靠 stash 直传

    await handler.handle_ai_message(
        content="图片已生成。",
        extra_references=[dict(STASH_REF)],
    )

    refs = persisted["references"]
    assert refs == [STASH_REF]  # 结构原样保留（含 id/meta_data）
    assert handler.last_persisted_message_id == "msg-1"


@pytest.mark.asyncio
async def test_extra_references_deduped_by_target_id(fake_extractor):
    persisted: dict = {}
    handler = _make_handler(persisted)
    # 正文里模型复述了同一张图 → extractor 提取出来，与 stash 重复
    fake_extractor(
        [
            {
                "type": "image",
                "target_id": PUBLIC_URL_A,
                "target_name": "a.png",
                "meta_data": {},
            },
            {
                "type": "image",
                "target_id": PUBLIC_URL_B,
                "target_name": "b.png",
                "meta_data": {},
            },
        ]
    )

    await handler.handle_ai_message(
        content=f"![]({PUBLIC_URL_A})",
        extra_references=[dict(STASH_REF)],
    )

    refs = persisted["references"]
    assert [r["target_id"] for r in refs] == [PUBLIC_URL_A, PUBLIC_URL_B]


@pytest.mark.asyncio
async def test_persist_branch_dispatch_carries_references(fake_extractor):
    """SSE 回归：persist 分支的 dispatch 块必须带合并后的 references。"""
    handler = _make_handler({})
    fake_extractor([])

    await handler.handle_ai_message(
        content="图片已生成。",
        extra_references=[dict(STASH_REF)],
    )

    # streaming + completed 双推是已知独立问题；此处锁定 completed 块必须带引用
    completed = [d for d in handler.dispatched if d.get("status") == "completed"]
    assert completed, "persist 分支未 dispatch completed 块"
    assert completed[-1]["references"] == [STASH_REF]


@pytest.mark.asyncio
async def test_no_extra_references_unchanged_behavior(fake_extractor):
    persisted: dict = {}
    handler = _make_handler(persisted)
    fake_extractor(
        [{"type": "image", "target_id": PUBLIC_URL_B, "target_name": "b", "meta_data": {}}]
    )

    await handler.handle_ai_message(content="![](b)")

    assert [r["target_id"] for r in persisted["references"]] == [PUBLIC_URL_B]


# ----------------------------------------------------------------------
# consume_pending_media_refs（stash 一次性消费）
# ----------------------------------------------------------------------
def _ctx_with(refs):
    metadata = SimpleNamespace(pending_media_refs=refs)
    return SimpleNamespace(metadata=metadata)


def test_consume_returns_and_clears_stash():
    ctx = _ctx_with([dict(STASH_REF)])
    refs = consume_pending_media_refs(ctx)
    assert refs == [STASH_REF]
    assert ctx.metadata.pending_media_refs == []


def test_consume_empty_is_noop_and_repeatable():
    ctx = _ctx_with(None)
    assert consume_pending_media_refs(ctx) == []
    assert consume_pending_media_refs(ctx) == []
