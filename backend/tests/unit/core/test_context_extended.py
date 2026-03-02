"""
Extended Unit tests for Context Management System.
Tests the full Context module including manager, plugins, and thread store.
"""

import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch, Mock
from dataclasses import dataclass

from app.core.context import (
    EvoContext,
    ContextManager,
    get_context,
    ContextPlugin,
    ContextPluginRegistry,
    plugin_registry,
)


class TestEvoContext:
    """Tests for EvoContext dataclass."""

    def test_default_creation(self):
        """Test creating context with defaults."""
        ctx = EvoContext()

        assert ctx.request_id is not None
        assert ctx.timestamp is not None
        assert ctx.user_id is None
        assert ctx.project_id is None
        assert ctx.thread_id is None
        assert ctx.language == "en"
        assert ctx.is_dry_run is False
        assert ctx.working_directory is None

    def test_custom_creation(self):
        """Test creating context with custom values."""
        ctx = EvoContext(
            request_id="test-123",
            user_id="user-456",
            project_id=1,
            thread_id="thread-789",
            language="zh",
            working_directory="/tmp/test",
            command_id=42,
            trace_id="trace-abc",
            is_dry_run=True,
        )

        assert ctx.request_id == "test-123"
        assert ctx.user_id == "user-456"
        assert ctx.project_id == 1
        assert ctx.thread_id == "thread-789"
        assert ctx.language == "zh"
        assert ctx.working_directory == "/tmp/test"
        assert ctx.command_id == 42
        assert ctx.trace_id == "trace-abc"
        assert ctx.is_dry_run is True

    def test_subconscious_pool_fields(self):
        """Test subconscious pool fields."""
        ctx = EvoContext(
            short_term_memory=["memory1", "memory2"],
            active_boundaries=["boundary1"],
            spatial_awareness=["spatial1"],
            environment_summaries=["env1"],
            memory_replay=["replay1"],
            identity_rules=["rule1"],
        )

        assert len(ctx.short_term_memory) == 2
        assert len(ctx.active_boundaries) == 1
        assert len(ctx.spatial_awareness) == 1
        assert len(ctx.environment_summaries) == 1
        assert len(ctx.memory_replay) == 1
        assert len(ctx.identity_rules) == 1

    def test_metadata_storage(self):
        """Test metadata dictionary."""
        ctx = EvoContext(metadata={"custom_key": "custom_value", "number": 42})

        assert ctx.metadata["custom_key"] == "custom_value"
        assert ctx.metadata["number"] == 42

    def test_to_dict(self):
        """Test serialization to dict."""
        ctx = EvoContext(
            request_id="test-123",
            user_id="user-456",
            project_id=1,
            language="zh",
            short_term_memory=["memory1"],
        )

        data = ctx.to_dict()

        assert data["request_id"] == "test-123"
        assert data["user_id"] == "user-456"
        assert data["project_id"] == 1
        assert data["language"] == "zh"
        assert data["short_term_memory"] == ["memory1"]
        assert "timestamp" in data

    def test_from_dict(self):
        """Test deserialization from dict."""
        data = {
            "request_id": "restored-123",
            "user_id": "user-789",
            "project_id": 2,
            "thread_id": "thread-xyz",
            "language": "fr",
            "is_dry_run": True,
            "working_directory": "/home",
            "metadata": {"key": "value"},
            "short_term_memory": ["memory1"],
        }

        ctx = EvoContext.from_dict(data)

        assert ctx.request_id == "restored-123"
        assert ctx.user_id == "user-789"
        assert ctx.project_id == 2
        assert ctx.thread_id == "thread-xyz"
        assert ctx.language == "fr"
        assert ctx.is_dry_run is True
        assert ctx.working_directory == "/home"
        assert ctx.metadata == {"key": "value"}
        assert ctx.short_term_memory == ["memory1"]

    def test_from_dict_extra_fields_ignored(self):
        """Test that extra fields in dict are ignored."""
        data = {
            "request_id": "test-123",
            "unknown_field": "should_be_ignored",
        }

        ctx = EvoContext.from_dict(data)

        assert ctx.request_id == "test-123"
        assert not hasattr(ctx, "unknown_field")


class TestContextManager:
    """Tests for ContextManager static class."""

    def test_current_returns_default_when_none(self):
        """Test current() returns default context when none is set."""
        ctx = ContextManager.current()

        assert isinstance(ctx, EvoContext)
        assert ctx.request_id == "global-fallback"

    def test_set_and_current(self):
        """Test setting and getting context."""
        ctx = EvoContext(request_id="test-set", user_id="user-1")

        token = ContextManager.set(ctx)
        try:
            current = ContextManager.current()
            assert current.request_id == "test-set"
            assert current.user_id == "user-1"
            assert current is ctx
        finally:
            ContextManager.reset(token)

    def test_reset_restores_previous(self):
        """Test reset restores previous context."""
        ctx1 = EvoContext(request_id="first")
        ctx2 = EvoContext(request_id="second")

        token1 = ContextManager.set(ctx1)
        try:
            assert ContextManager.current().request_id == "first"

            token2 = ContextManager.set(ctx2)
            assert ContextManager.current().request_id == "second"

            ContextManager.reset(token2)
            assert ContextManager.current().request_id == "first"
        finally:
            ContextManager.reset(token1)

    def test_get_var_with_attribute(self):
        """Test get_var retrieves attribute."""
        ctx = EvoContext(project_id=42, user_id="test-user")
        token = ContextManager.set(ctx)

        try:
            assert ContextManager.get_var("project_id") == 42
            assert ContextManager.get_var("user_id") == "test-user"
        finally:
            ContextManager.reset(token)

    def test_get_var_with_default(self):
        """Test get_var returns default for missing key."""
        ctx = EvoContext()
        token = ContextManager.set(ctx)

        try:
            assert ContextManager.get_var("nonexistent", "default") == "default"
        finally:
            ContextManager.reset(token)

    def test_get_var_from_metadata(self):
        """Test get_var retrieves from metadata."""
        ctx = EvoContext(metadata={"custom": "value"})
        token = ContextManager.set(ctx)

        try:
            assert ContextManager.get_var("custom") == "value"
        finally:
            ContextManager.reset(token)

    @pytest.mark.asyncio
    async def test_save_to_redis(self):
        """Test saving context to Redis."""
        ctx = EvoContext(request_id="redis-test", thread_id="thread-123")
        token = ContextManager.set(ctx)

        try:
            with patch("app.core.context.manager.redis_client") as mock_redis:
                mock_redis.hset = AsyncMock()
                mock_redis.expire = AsyncMock()

                await ContextManager.save_to_redis("thread-123")

                mock_redis.hset.assert_called_once()
                mock_redis.expire.assert_called_once()
                # Check key format
                call_args = mock_redis.hset.call_args
                assert "evo:context:thread-123" in str(call_args)
        finally:
            ContextManager.reset(token)

    @pytest.mark.asyncio
    async def test_save_to_redis_skips_fallback(self):
        """Test that fallback context is not saved to Redis."""
        # Don't set any context - will use fallback
        with patch("app.core.context.manager.redis_client") as mock_redis:
            mock_redis.hset = AsyncMock()
            mock_redis.expire = AsyncMock()

            await ContextManager.save_to_redis("thread-123")

            mock_redis.hset.assert_not_called()
            mock_redis.expire.assert_not_called()

    @pytest.mark.asyncio
    async def test_load_from_redis(self):
        """Test loading context from Redis."""
        import json

        ctx_data = {
            "request_id": "loaded-123",
            "user_id": "loaded-user",
            "project_id": "99",
            "thread_id": "loaded-thread",
            "timestamp": "1234567890.0",
        }

        with patch("app.core.context.manager.redis_client") as mock_redis:
            mock_redis.hgetall = AsyncMock(return_value=ctx_data)

            loaded = await ContextManager.load_from_redis("loaded-thread")

            assert loaded is not None
            assert loaded.request_id == "loaded-123"
            assert loaded.user_id == "loaded-user"
            assert loaded.project_id == 99
            assert loaded.thread_id == "loaded-thread"

    @pytest.mark.asyncio
    async def test_load_from_redis_not_found(self):
        """Test loading when key doesn't exist."""
        with patch("app.core.context.manager.redis_client") as mock_redis:
            mock_redis.hgetall = AsyncMock(return_value=None)

            loaded = await ContextManager.load_from_redis("nonexistent")

            assert loaded is None

    def test_get_context_alias(self):
        """Test get_context is alias for current()."""
        ctx = EvoContext(request_id="alias-test")
        token = ContextManager.set(ctx)

        try:
            from app.core.context import get_context
            assert get_context() is ctx
        finally:
            ContextManager.reset(token)


class TestContextPlugin:
    """Tests for ContextPlugin protocol and registry."""

    def test_plugin_protocol(self):
        """Test ContextPlugin protocol implementation."""
        @dataclass
        class TestPlugin:
            name: str = "TestPlugin"

            def hydrate(self, ctx: EvoContext) -> None:
                ctx.environment_summaries.append(f"Hydrated by {self.name}")

        # Verify it conforms to protocol
        plugin = TestPlugin()
        ctx = EvoContext()
        plugin.hydrate(ctx)

        assert "Hydrated by TestPlugin" in ctx.environment_summaries

    def test_plugin_registry_register(self):
        """Test registering plugins."""
        registry = ContextPluginRegistry()

        class TestPlugin:
            def hydrate(self, ctx):
                ctx.short_term_memory.append("test")

        plugin = TestPlugin()
        registry.register(plugin)

        assert len(registry._plugins) == 1

    def test_plugin_registry_hydrate(self):
        """Test hydrating context with plugins."""
        registry = ContextPluginRegistry()

        class Plugin1:
            def hydrate(self, ctx):
                ctx.short_term_memory.append("plugin1")

        class Plugin2:
            def hydrate(self, ctx):
                ctx.active_boundaries.append("boundary1")

        registry.register(Plugin1())
        registry.register(Plugin2())

        ctx = EvoContext()
        registry.hydrate_context(ctx)

        assert "plugin1" in ctx.short_term_memory
        assert "boundary1" in ctx.active_boundaries

    def test_plugin_registry_error_handling(self):
        """Test plugin errors don't break hydration."""
        registry = ContextPluginRegistry()

        class ErrorPlugin:
            def hydrate(self, ctx):
                raise ValueError("Plugin error")

        class GoodPlugin:
            def hydrate(self, ctx):
                ctx.short_term_memory.append("good")

        registry.register(ErrorPlugin())
        registry.register(GoodPlugin())

        ctx = EvoContext()
        # Should not raise
        registry.hydrate_context(ctx)

        assert "good" in ctx.short_term_memory

    def test_global_plugin_registry(self):
        """Test global plugin_registry instance."""
        from app.core.context import plugin_registry

        assert isinstance(plugin_registry, ContextPluginRegistry)


class TestWorkspaceProvider:
    """Tests for WorkspaceProvider protocol."""

    @pytest.mark.asyncio
    async def test_workspace_provider_protocol(self):
        """Test WorkspaceProvider protocol."""
        from app.core.context.plugins import set_workspace_provider, get_workspace_provider

        class TestProvider:
            async def get_project_structure(self, path: str) -> str:
                return f"Structure for {path}"

        provider = TestProvider()
        set_workspace_provider(provider)

        retrieved = get_workspace_provider()
        assert retrieved is provider

        result = await retrieved.get_project_structure("/test")
        assert result == "Structure for /test"

    def test_get_workspace_provider_none(self):
        """Test get_workspace_provider returns None when not set."""
        from app.core.context.plugins import get_workspace_provider, _workspace_provider

        # Temporarily clear the provider
        original = _workspace_provider
        try:
            from app.core.context import plugins
            plugins._workspace_provider = None

            assert get_workspace_provider() is None
        finally:
            plugins._workspace_provider = original


class TestContextIsolation:
    """Tests for context isolation in async environments."""

    @pytest.mark.asyncio
    async def test_context_isolation_async(self):
        """Test context isolation between async tasks."""
        async def task_a():
            ctx = EvoContext(request_id="task-a")
            token = ContextManager.set(ctx)
            await asyncio.sleep(0.01)  # Simulate work
            result = ContextManager.current().request_id
            ContextManager.reset(token)
            return result

        async def task_b():
            ctx = EvoContext(request_id="task-b")
            token = ContextManager.set(ctx)
            await asyncio.sleep(0.01)  # Simulate work
            result = ContextManager.current().request_id
            ContextManager.reset(token)
            return result

        # Run concurrently
        results = await asyncio.gather(task_a(), task_b())

        assert "task-a" in results
        assert "task-b" in results
