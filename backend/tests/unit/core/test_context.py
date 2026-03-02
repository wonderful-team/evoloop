"""
Unit tests for context management system.
"""

import pytest
from unittest.mock import patch, MagicMock, AsyncMock

from app.core.context.manager import EvoContext, ContextManager
from tests.fixtures.factories import EvoContextFactory


class TestEvoContext:
    """Tests for EvoContext dataclass."""

    def test_create_default_context(self):
        """Test creating context with defaults."""
        ctx = EvoContext()

        assert ctx.request_id is not None
        assert ctx.timestamp is not None
        assert ctx.user_id is None
        assert ctx.project_id is None
        assert ctx.language == "en"

    def test_create_custom_context(self):
        """Test creating context with custom values."""
        ctx = EvoContext(
            request_id="test-123",
            user_id="user-456",
            project_id=1,
            thread_id="thread-789",
            language="zh",
        )

        assert ctx.request_id == "test-123"
        assert ctx.user_id == "user-456"
        assert ctx.project_id == 1
        assert ctx.thread_id == "thread-789"
        assert ctx.language == "zh"

    def test_to_dict(self):
        """Test converting context to dictionary."""
        ctx = EvoContextFactory.create(
            request_id="test-123",
            user_id="user-456",
        )

        data = ctx.to_dict()

        assert data["request_id"] == "test-123"
        assert data["user_id"] == "user-456"
        assert "timestamp" in data
        assert "short_term_memory" in data

    def test_from_dict(self):
        """Test creating context from dictionary."""
        data = {
            "request_id": "restored-123",
            "user_id": "user-789",
            "project_id": 2,
            "language": "fr",
            "metadata": {"key": "value"},
        }

        ctx = EvoContext.from_dict(data)

        assert ctx.request_id == "restored-123"
        assert ctx.user_id == "user-789"
        assert ctx.project_id == 2
        assert ctx.language == "fr"
        assert ctx.metadata == {"key": "value"}


class TestContextManager:
    """Tests for ContextManager."""

    def test_get_current_empty(self):
        """Test getting current context when none is set."""
        # Reset any existing context
        ctx = ContextManager.current()

        assert isinstance(ctx, EvoContext)
        # Should return fallback context
        assert ctx.request_id == "global-fallback"

    def test_set_and_get_context(self):
        """Test setting and retrieving context."""
        ctx = EvoContextFactory.create(request_id="test-set")

        token = ContextManager.set(ctx)
        try:
            current = ContextManager.current()
            assert current.request_id == "test-set"
            assert current is ctx
        finally:
            ContextManager.reset(token)

    def test_reset_context(self):
        """Test resetting context to previous state."""
        ctx1 = EvoContextFactory.create(request_id="first")
        ctx2 = EvoContextFactory.create(request_id="second")

        token1 = ContextManager.set(ctx1)
        try:
            assert ContextManager.current().request_id == "first"

            token2 = ContextManager.set(ctx2)
            assert ContextManager.current().request_id == "second"

            ContextManager.reset(token2)
            assert ContextManager.current().request_id == "first"
        finally:
            ContextManager.reset(token1)

    def test_get_var_with_default(self):
        """Test getting variables with defaults."""
        ctx = EvoContextFactory.create(project_id=42)
        token = ContextManager.set(ctx)

        try:
            # Test attribute access
            assert ContextManager.get_var("project_id") == 42

            # Test default value
            assert ContextManager.get_var("nonexistent", "default") == "default"

            # Test metadata access
            ctx.metadata["custom_key"] = "custom_value"
            assert ContextManager.get_var("custom_key") == "custom_value"
        finally:
            ContextManager.reset(token)

    @pytest.mark.asyncio
    async def test_save_and_load_from_redis(self):
        """Test persisting context to Redis."""
        ctx = EvoContextFactory.create(
            request_id="redis-test",
            thread_id="thread-redis",
        )
        token = ContextManager.set(ctx)

        try:
            # Mock Redis client with async methods
            import json
            mock_redis = MagicMock()
            # Phase 4: Uses hset and expire instead of setex
            mock_redis.hset = AsyncMock(return_value=True)
            mock_redis.expire = AsyncMock(return_value=True)
            # hgetall returns dict, not string
            mock_redis.hgetall = AsyncMock(return_value={
                k: json.dumps(v) if isinstance(v, (list, dict)) else str(v)
                for k, v in ctx.to_dict().items()
            })

            # Patch where redis_client is used (in manager module)
            with patch("app.core.context.manager.redis_client", mock_redis):
                # Save
                await ContextManager.save_to_redis("thread-redis")
                mock_redis.hset.assert_called_once()
                mock_redis.expire.assert_called_once()

                # Load
                loaded = await ContextManager.load_from_redis("thread-redis")
                assert loaded is not None
                assert loaded.thread_id == "thread-redis"
        finally:
            ContextManager.reset(token)


class TestContextPluginRegistry:
    """Tests for ContextPluginRegistry."""

    def test_register_plugin(self):
        """Test registering a context plugin."""
        from app.core.context.plugins import ContextPluginRegistry, ContextPlugin

        registry = ContextPluginRegistry()

        class TestPlugin(ContextPlugin):
            def hydrate(self, ctx):
                ctx.environment_summaries.append("test")

        plugin = TestPlugin()
        registry.register(plugin)

        assert len(registry._plugins) == 1

    def test_hydrate_context(self):
        """Test hydrating context with plugins."""
        from app.core.context.plugins import ContextPluginRegistry, ContextPlugin

        registry = ContextPluginRegistry()

        class TestPlugin(ContextPlugin):
            def hydrate(self, ctx):
                ctx.environment_summaries.append("hydrated")

        ctx = EvoContextFactory.create()
        registry.register(TestPlugin())
        registry.hydrate_context(ctx)

        assert "hydrated" in ctx.environment_summaries

    def test_plugin_error_handling(self):
        """Test that plugin errors don't break hydration."""
        from app.core.context.plugins import ContextPluginRegistry, ContextPlugin

        registry = ContextPluginRegistry()

        class ErrorPlugin(ContextPlugin):
            def hydrate(self, ctx):
                raise ValueError("Plugin error")

        class GoodPlugin(ContextPlugin):
            def hydrate(self, ctx):
                ctx.environment_summaries.append("good")

        ctx = EvoContextFactory.create()
        registry.register(ErrorPlugin())
        registry.register(GoodPlugin())

        # Should not raise
        registry.hydrate_context(ctx)

        assert "good" in ctx.environment_summaries
