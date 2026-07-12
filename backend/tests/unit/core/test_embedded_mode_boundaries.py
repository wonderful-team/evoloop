"""
运行时模式切换边界验证 (Phase 12)

验证系统在运行时不支持 EMBEDDED_MODE 切换（工厂使用模块级单例），
并确认这是设计意图。
"""

from unittest.mock import patch

import pytest

from app.core.config import settings


class TestModeSwitchingBoundary:
    """验证运行时模式切换的行为边界。"""

    def test_switching_mode_after_singleton_created_does_not_change_backend(self):
        """EMBEDDED_MODE 切换后，已创建的 singleton 不会自动切换。"""
        with patch.object(settings, "EMBEDDED_MODE", True):
            from app.infrastructure.cache import get_cache

            get_cache.__globals__["_cache_instance"] = None
            cache_embedded = get_cache()

        # 切换模式
        with patch.object(settings, "EMBEDDED_MODE", False):
            # Singleton 已经创建，不会重新评估
            cache_after_switch = get_cache()

        assert cache_after_switch is cache_embedded  # 同一个实例

    def test_reset_singleton_allows_mode_change(self):
        """重置 singleton 后，新模式会生效。"""
        with patch.object(settings, "EMBEDDED_MODE", True):
            from app.infrastructure.cache import get_cache

            get_cache.__globals__["_cache_instance"] = None
            cache1 = get_cache()

        # 重置 singleton
        get_cache.__globals__["_cache_instance"] = None

        with patch.object(settings, "EMBEDDED_MODE", False):
            # 这里会尝试创建 RedisCache，但在测试环境可能失败
            # 我们验证的是工厂会尝试不同的路径
            with patch("app.infrastructure.cache.redis.RedisCache") as MockRedis:
                get_cache()
                MockRedis.assert_called_once()

    def test_vector_store_singleton_resettable(self):
        """Vector store singleton 可以重置。"""
        from app.infrastructure.database.vector import get_vector_store
        from app.infrastructure.database.vector.lancedb_store import LanceVectorStore

        # Reset
        LanceVectorStore._instance = None
        get_vector_store.__globals__["_vector_store"] = None

        with patch.object(settings, "EMBEDDED_MODE", True):
            store = get_vector_store()
            assert store is not None

    def test_message_broker_singleton_resettable(self):
        """Message broker singleton 可以重置。"""
        from app.core.engine.message.broker import get_message_broker, _message_broker

        # Reset
        get_message_broker.__globals__["_message_broker"] = None

        with patch.object(settings, "EMBEDDED_MODE", True):
            with patch("app.core.engine.message.broker.LocalMessageBroker") as MockLocal:
                get_message_broker()
                MockLocal.assert_called_once()

