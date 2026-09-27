"""ErrorEmitter 错误呈现契约测试。

锁定契约：**任何**被上抛到会话层的异常，经 ErrorEmitter.emit 后必须产生
对应的用户可见呈现事件（SSE）：

- quota_exhausted（含订阅过期）  → QuotaExhaustedEvent
- llm_auth                      → LLMAuthErrorEvent
- 其他（限流/超时/网络/未知）     → system 错误消息块（category="error"）

这是「后端报错、前端没反应」问题的防复发锁：新增错误类型时在此追加参数，
修改呈现链路时跑本文件即可发现契约破坏。
"""

from __future__ import annotations

import logging
from typing import Any

import pytest

from app.core.engine.error_emitter import ErrorEmitter
from app.core.engine.error_handler import LLMErrorHandler
from app.core.engine.message.constants import MessageRole
from app.core.engine.message.schemas import MessageBlock
from app.core.exceptions import InferenceError
from app.models.schemas.events import (
    AuthExpiredEvent,
    LLMAuthErrorEvent,
    QuotaExhaustedEvent,
)


class FakePublisher:
    """捕获 emit 发布的事件序列，替代 MessagePublisher。"""

    def __init__(self, thread_id: str, project_id: Any = None) -> None:
        self.thread_id = thread_id
        self.project_id = project_id
        self.published: list[tuple[Any, set[str]]] = []

    async def publish(
        self,
        payload: Any,
        channels: set[str] | None = None,
        action: str = "create",
    ) -> None:
        self.published.append((payload, set(channels or set())))


SUBSCRIPTION_403 = Exception(
    'Error code: 403 - {"error": {"message": "subscription has expired, please renew", '
    '"type": "api_error", "code": "subscription_expired"}}'
)


@pytest.fixture
def fake(monkeypatch) -> FakePublisher:
    """替换 MessagePublisher 为捕获型 FakePublisher。"""
    publisher = FakePublisher(thread_id="t-1")
    monkeypatch.setattr(
        "app.core.engine.error_emitter.MessagePublisher",
        lambda thread_id, project_id=None: publisher,
    )
    return publisher


@pytest.fixture
def emitter() -> ErrorEmitter:
    return ErrorEmitter()


def _types(fake: FakePublisher) -> list[type]:
    return [type(payload) for payload, _ in fake.published]


class TestQuotaErrors:
    """配额/订阅类错误 → QuotaExhaustedEvent（前端续费横幅）。"""

    @pytest.mark.parametrize(
        "error",
        [
            SUBSCRIPTION_403,
            Exception("insufficient_quota: You exceeded your current quota"),
            InferenceError(
                error_type="quota_exhausted",
                status_code=403,
                user_friendly_msg="额度耗尽",
                raw_error="403 quota",
            ),
        ],
        ids=["subscription_expired", "insufficient_quota", "inference_pre_classified"],
    )
    async def test_quota_emits_quota_event(self, emitter, fake, error) -> None:
        await emitter.emit("t-1", error)

        assert _types(fake) == [QuotaExhaustedEvent]
        event = fake.published[0][0]
        assert event.thread_id == "t-1"
        assert event.title
        assert event.message


class TestLLMAuthErrors:
    """LLM 鉴权失败 → LLMAuthErrorEvent（前端 toast + 设置跳转）。"""

    async def test_pre_classified_llm_auth(self, emitter, fake) -> None:
        await emitter.emit(
            "t-1",
            InferenceError(
                error_type="llm_auth",
                status_code=401,
                user_friendly_msg="API Key 无效",
                raw_error="401 invalid api key",
            ),
        )
        assert _types(fake) == [LLMAuthErrorEvent]
        assert fake.published[0][0].message

    async def test_raw_auth_error_classified(self, emitter, fake) -> None:
        await emitter.emit("t-1", Exception("Error code: 401 - invalid api key, unauthorized"))
        assert _types(fake) == [LLMAuthErrorEvent]


class TestAuthExpired:
    """平台登录态过期 → AuthExpiredEvent。"""

    async def test_pre_classified_auth_expired(self, emitter, fake) -> None:
        await emitter.emit(
            "t-1",
            InferenceError(
                error_type="auth_expired",
                status_code=401,
                user_friendly_msg="登录已过期",
                raw_error="401 please login first",
            ),
        )
        assert _types(fake) == [AuthExpiredEvent]


class TestGenericErrors:
    """非终端错误（限流/超时/网络/未知）→ system 错误消息块（SSE-only）。"""

    @pytest.mark.parametrize(
        "error",
        [
            Exception("Error code: 429 - rate limit exceeded"),
            Exception("Request timed out after 60s"),
            Exception("totally unexpected failure"),
            InferenceError(
                error_type="rate_limit",
                status_code=429,
                user_friendly_msg="请求过于频繁",
                raw_error="429",
            ),
        ],
        ids=["rate_limit", "timeout", "unknown", "inference_rate_limit"],
    )
    async def test_generic_emits_system_block(self, emitter, fake, error) -> None:
        await emitter.emit("t-1", error)

        assert _types(fake) == [MessageBlock]
        block, channels = fake.published[0]
        assert block.role == MessageRole.SYSTEM
        assert block.category == "error"
        assert block.thread_id == "t-1"
        assert block.content  # 必须有可读文案
        # 错误块仅走 SSE（错误详情不进 mobile/voice 通道）
        assert channels == {"sse"}


class TestEmitterRobustness:
    """发布失败不得上抛（崩溃兜底路径必须自身安全）。"""

    async def test_publish_failure_swallowed(
        self, emitter, fake, monkeypatch, caplog
    ) -> None:
        async def boom(*args, **kwargs):
            raise ConnectionError("broker down")

        monkeypatch.setattr(fake, "publish", boom)
        with caplog.at_level(logging.ERROR, logger="app.core.engine.error_emitter"):
            await emitter.emit("t-1", Exception("anything"))
        assert caplog.text


class TestClassifierContract:
    """分类器契约：关键错误词 → 类型映射（分类是呈现的源头）。"""

    def test_subscription_expired_maps_to_quota(self) -> None:
        c = LLMErrorHandler.classify_exception(SUBSCRIPTION_403)
        assert c.error_type == "quota_exhausted"
        assert c.is_terminal is True
