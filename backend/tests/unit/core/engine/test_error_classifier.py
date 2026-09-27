"""LLMErrorHandler.classify_exception 全表契约测试。

锁定「错误文本 → error_type」映射与终态性——分类是呈现链路的源头
（ErrorEmitter 依据 error_type 决定事件类型），关键词漂移会让下游契约
（test_error_emitter.py）静默失效，本文件是第一道锁。
"""

from __future__ import annotations

import pytest

from app.core.engine.error_handler import LLMErrorHandler


def _classify(msg: str):
    return LLMErrorHandler.classify_exception(Exception(msg))


class TestQuotaExhausted:
    @pytest.mark.parametrize(
        "text",
        [
            "insufficient_quota: You exceeded your current quota",
            "your usage limit has been reached",
            "billing cycle ended",
            "not enough credit",
            "insufficient balance",
            "Error code: 403 - subscription has expired, please renew",
            "Error code: 403 - subscription_expired",
            "quota exceeded for this org",
        ],
    )
    def test_quota_keywords(self, text) -> None:
        c = _classify(text)
        assert c.error_type == "quota_exhausted"
        assert c.is_terminal is True
        assert c.status_code == 403


class TestLLMAuth:
    @pytest.mark.parametrize(
        "text",
        [
            "Error code: 401 - unauthorized, invalid api key",
            "401 unauthorized: api key rejected",
        ],
    )
    def test_auth_keywords(self, text) -> None:
        c = _classify(text)
        assert c.error_type == "llm_auth"
        assert c.is_terminal is True
        assert c.status_code == 401


class TestPlatformAuth:
    def test_platform_login_first(self) -> None:
        c = _classify("please login first before calling this api")
        assert c.error_type == "auth_expired"
        assert c.is_terminal is True

    def test_platform_not_authenticated(self) -> None:
        c = _classify("not authenticated with evoloop platform")
        assert c.error_type == "auth_expired"
        assert c.is_terminal is True


class TestRateLimit:
    @pytest.mark.parametrize(
        "text",
        [
            "Error code: 429 - rate limit exceeded",
            "too many requests, slow down",
        ],
    )
    def test_rate_limit_keywords(self, text) -> None:
        c = _classify(text)
        assert c.error_type == "rate_limit"
        assert c.is_terminal is False
        assert c.status_code == 429


class TestServiceUnavailable:
    @pytest.mark.parametrize(
        "text",
        [
            "upstream service unavailable",
            "provider overloaded",
            "bad gateway",
            "Error code: 503 - service error",
        ],
    )
    def test_service_keywords(self, text) -> None:
        c = _classify(text)
        assert c.error_type == "service_unavailable"
        assert c.status_code == 503


class TestNetwork:
    @pytest.mark.parametrize(
        "text",
        [
            "request timed out after 60s",
            "connection reset by peer",
            "socket closed unexpectedly",
            "httpx remote protocol error",
        ],
    )
    def test_network_keywords(self, text) -> None:
        c = _classify(text)
        assert c.error_type == "network_error"


class TestModelNotFound:
    def test_model_not_found(self) -> None:
        c = _classify("Error code: 404 - model_not_found: no such model")
        assert c.error_type == "model_not_found"
        assert c.is_terminal is True
        assert c.status_code == 404


class TestContextLimit:
    @pytest.mark.parametrize(
        "text",
        [
            "exceeds context length of 8192 tokens",
            "n_ctx is too small",
            "n_keep exceeds the prompt window",
        ],
    )
    def test_context_keywords(self, text) -> None:
        c = _classify(text)
        assert c.error_type == "context_limit"
        assert c.is_terminal is True


class TestInvalidConfig:
    def test_invalid_config(self) -> None:
        c = _classify("invalid_config: missing base_url")
        assert c.error_type == "invalid_config"
        assert c.is_terminal is True


class TestFallback:
    """无法识别的错误归 generic，非终态（可走 system 消息块呈现）。"""

    def test_unknown_falls_back(self) -> None:
        c = _classify("totally unexpected failure")
        assert c.error_type == "llm_invocation_system"
        assert c.is_terminal is False
