"""Godcmd tests — command registry, handler, auth."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.core.godcmd import (
    GodcmdHandler,
    GodcmdContext,
    godcmd_registry,
    is_admin_user,
)
from app.core.godcmd.registry import GodcmdCommand


class TestGodcmdRegistry:
    """GodcmdRegistry — command registration and lookup."""

    def test_register_and_get(self):
        reg = godcmd_registry.__class__()
        async def handler(ctx): return "ok"
        reg.register("test", handler, description="test cmd")

        cmd = reg.get("test")
        assert cmd is not None
        assert cmd.name == "test"
        assert cmd.description == "test cmd"

    def test_register_with_aliases(self):
        reg = godcmd_registry.__class__()
        async def handler(ctx): return "ok"
        reg.register("stop", handler, aliases=["cancel"])

        assert reg.get("stop") is not None
        assert reg.get("cancel") is not None
        assert reg.get("stop") is reg.get("cancel")

    def test_get_unknown_returns_none(self):
        reg = godcmd_registry.__class__()
        assert reg.get("nonexistent") is None

    def test_all_commands_excludes_aliases(self):
        reg = godcmd_registry.__class__()
        async def h(ctx): return "ok"
        reg.register("stop", h, aliases=["cancel", "abort"])
        reg.register("start", h)

        cmds = reg.all_commands()
        names = [c.name for c in cmds]
        assert "stop" in names
        assert "start" in names
        assert len(cmds) == 2

    def test_list_help_includes_commands(self):
        reg = godcmd_registry.__class__()
        async def h(ctx): return "ok"
        reg.register("stop", h, description="Stop a run")
        reg.register("help", h, description="Show help", admin_only=False)

        text = reg.list_help()
        assert "#stop" in text
        assert "#help" in text
        assert "Stop a run" in text


class TestGodcmdHandler:
    """GodcmdHandler — message interception and command dispatch."""

    def test_is_godcmd_detects_prefix(self):
        handler = GodcmdHandler()
        assert handler.is_godcmd("#stop")
        assert handler.is_godcmd("  #help  ")
        assert not handler.is_godcmd("regular message")
        assert not handler.is_godcmd("")

    @pytest.mark.asyncio
    async def test_handle_unknown_command(self):
        handler = GodcmdHandler()
        reply = await handler.handle("t1", "#nonexistent", user=MagicMock(id=1))
        assert "Unknown command" in reply

    @pytest.mark.asyncio
    async def test_handle_empty_command(self):
        handler = GodcmdHandler()
        reply = await handler.handle("t1", "#", user=MagicMock(id=1))
        assert "Empty command" in reply

    @pytest.mark.asyncio
    async def test_handle_non_admin_denied(self):
        handler = GodcmdHandler()
        user = MagicMock()
        user.is_superuser = False
        user.id = 999

        with patch("app.core.godcmd.handler.is_admin_user", AsyncMock(return_value=False)):
            reply = await handler.handle("t1", "#stopall", user=user)

        assert "Permission denied" in reply

    @pytest.mark.asyncio
    async def test_handle_admin_executes(self):
        handler = GodcmdHandler()
        user = MagicMock()
        user.is_superuser = True
        user.id = 1

        from app.core.concurrency import cancel_registry
        with patch("app.core.godcmd.handler.is_admin_user", AsyncMock(return_value=True)):
            with patch.object(cancel_registry, "cancel_all", AsyncMock(return_value=3)):
                reply = await handler.handle("t1", "#stopall", user=user)

        assert "3" in reply

    @pytest.mark.asyncio
    async def test_handle_passes_args(self):
        handler = GodcmdHandler()

        captured = {}

        async def mock_handler(ctx):
            captured["args"] = ctx.args
            return "ok"

        with patch.object(godcmd_registry, "get") as mock_get:
            mock_get.return_value = GodcmdCommand(
                name="config", handler=mock_handler, admin_only=False
            )
            reply = await handler.handle("t1", "#config LLM_MODEL gpt-4", user=MagicMock(id=1))

        assert reply == "ok"
        assert captured["args"] == ["LLM_MODEL", "gpt-4"]

    @pytest.mark.asyncio
    async def test_handle_command_exception_returns_error(self):
        handler = GodcmdHandler()

        async def failing_handler(ctx):
            raise RuntimeError("boom")

        with patch.object(godcmd_registry, "get") as mock_get:
            mock_get.return_value = GodcmdCommand(
                name="test", handler=failing_handler, admin_only=False
            )
            reply = await handler.handle("t1", "#test", user=MagicMock(id=1))

        assert "failed" in reply
        assert "boom" in reply


class TestGodcmdAuth:
    """is_admin_user — admin identification."""

    @pytest.mark.asyncio
    async def test_none_user_is_not_admin(self):
        assert not await is_admin_user(None)

    @pytest.mark.asyncio
    async def test_superuser_is_admin(self):
        user = MagicMock()
        user.is_superuser = True
        assert await is_admin_user(user)

    @pytest.mark.asyncio
    async def test_non_superuser_not_admin_in_multi_tenant(self):
        user = MagicMock()
        user.is_superuser = False
        user.id = 999

        with patch("app.infrastructure.config.service.SystemConfigService.get_value", return_value=""):
            with patch("app.core.config.settings.MULTI_TENANT_MODE", True):
                assert not await is_admin_user(user)

    @pytest.mark.asyncio
    async def test_admin_member_ids_config(self):
        user = MagicMock()
        user.is_superuser = False
        user.id = 42

        with patch("app.infrastructure.config.service.SystemConfigService.get_value", return_value="42,100"):
            with patch("app.core.config.settings.MULTI_TENANT_MODE", True):
                assert await is_admin_user(user)

    @pytest.mark.asyncio
    async def test_single_user_mode_is_admin(self):
        user = MagicMock()
        user.is_superuser = False
        user.id = 1

        with patch("app.core.config.settings.MULTI_TENANT_MODE", False):
            assert await is_admin_user(user)


class TestBuiltinCommands:
    """Built-in godcmd commands."""

    @pytest.mark.asyncio
    async def test_help_command(self):
        from app.core.godcmd.commands import cmd_help
        ctx = GodcmdContext(thread_id="t1")
        result = await cmd_help(ctx)
        assert "#help" in result
        assert "#status" in result

    @pytest.mark.asyncio
    async def test_stop_current_thread(self):
        from app.core.godcmd.commands import cmd_stop
        from app.core.concurrency import cancel_registry
        ctx = GodcmdContext(thread_id="t1", member_id=1)

        with patch.object(cancel_registry, "cancel", AsyncMock(return_value=True)):
            with patch("app.core.monitoring.activity.activity_monitor.stop_run", AsyncMock()):
                result = await cmd_stop(ctx)

        assert "cancelled" in result.lower()

    @pytest.mark.asyncio
    async def test_stopall_cancels_all(self):
        from app.core.godcmd.commands import cmd_stopall
        from app.core.concurrency import cancel_registry
        ctx = GodcmdContext(thread_id="t1", member_id=1)

        with patch.object(cancel_registry, "cancel_all", AsyncMock(return_value=5)):
            result = await cmd_stopall(ctx)

        assert "5" in result

    @pytest.mark.asyncio
    async def test_config_get(self):
        from app.core.godcmd.commands import cmd_config
        ctx = GodcmdContext(thread_id="t1", args=["LLM_MODEL"])

        with patch("app.infrastructure.config.service.SystemConfigService.get_value", return_value="gpt-4"):
            result = await cmd_config(ctx)

        assert "LLM_MODEL" in result
        assert "gpt-4" in result

    @pytest.mark.asyncio
    async def test_config_set(self):
        from app.core.godcmd.commands import cmd_config
        ctx = GodcmdContext(thread_id="t1", args=["LLM_MODEL", "claude-3"])

        with patch("app.infrastructure.config.service.SystemConfigService.set_value_async", AsyncMock()):
            result = await cmd_config(ctx)

        assert "Set" in result
        assert "LLM_MODEL" in result
        assert "claude-3" in result
