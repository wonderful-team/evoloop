"""
Built-in godcmd commands.

#help     — list available commands
#status   — show active runs, queue depth, dream status
#stop     — cancel a specific run (or current run)
#stopall  — cancel all active runs
#config   — get/set system config
#reload   — trigger config hot-reload
#dream    — trigger a Deep Dream cycle
"""

import logging

from app.core.godcmd.registry import GodcmdContext, register_godcmd

logger = logging.getLogger(__name__)


@register_godcmd("help", description="List available admin commands", admin_only=False)
async def cmd_help(ctx: GodcmdContext) -> str:
    """List all available godcmd commands."""
    from app.core.godcmd.registry import godcmd_registry
    return godcmd_registry.list_help()


@register_godcmd("status", description="Show system status (active runs, queue, dream)", aliases=["st"])
async def cmd_status(ctx: GodcmdContext) -> str:
    """Show system status."""
    from app.core.concurrency import cancel_registry
    from app.core.memory.dream.scheduler import get_dream_status

    lines = ["== System Status ==", ""]

    active = cancel_registry.active_runs()
    lines.append(f"Active runs: {len(active)}")
    for tid in active[:10]:
        lines.append(f"  - {tid}")
    if len(active) > 10:
        lines.append(f"  ... and {len(active) - 10} more")

    lines.append("")

    try:
        dream = get_dream_status()
        lines.append(f"Deep Dream: last={dream.get('last_dream', 'never')}")
        lines.append(f"  should_run={dream.get('should_run', '?')}")
    except (ValueError, OSError, RuntimeError, TypeError, KeyError, AttributeError) as e:
        lines.append(f"Deep Dream: error reading status ({e})")

    return "\n".join(lines)


@register_godcmd("stop", description="Cancel a run (default: current thread)", aliases=["cancel"])
async def cmd_stop(ctx: GodcmdContext) -> str:
    """Cancel a run by thread_id, or the current thread if no arg."""
    from app.core.concurrency import cancel_registry
    from app.core.monitoring.activity import activity_monitor

    target = ctx.args[0] if ctx.args else ctx.thread_id

    cancelled = await cancel_registry.cancel(target, requester_id=ctx.member_id)
    await activity_monitor.stop_run(target)

    if cancelled:
        return f"Run {target} cancelled."
    else:
        await activity_monitor.stop_run(target)
        return f"Stop signal sent for {target} (not in local registry, using DB flag)."


@register_godcmd("stopall", description="Cancel all active runs")
async def cmd_stopall(ctx: GodcmdContext) -> str:
    """Cancel all active runs."""
    from app.core.concurrency import cancel_registry

    count = await cancel_registry.cancel_all()
    return f"Cancelled {count} active run(s)."


@register_godcmd("config", description="Get/set system config: #config <key> [value]")
async def cmd_config(ctx: GodcmdContext) -> str:
    """Get or set a system config value."""
    from app.infrastructure.config.service import SystemConfigService

    if not ctx.args:
        return "Usage: #config <key> [value]"

    key = ctx.args[0]

    if len(ctx.args) == 1:
        value = SystemConfigService.get_value(key)
        return f"{key} = {value}"
    else:
        value = ctx.args[1]
        await SystemConfigService.set_value_async(key, value)
        return f"Set {key} = {value}"


@register_godcmd("reload", description="Trigger config hot-reload")
async def cmd_reload(ctx: GodcmdContext) -> str:
    """Trigger a config reload."""
    from app.core.events.publishers import publish_config_changed

    await publish_config_changed("__reload__", "", "")
    return "Config reload signal sent."


@register_godcmd("dream", description="Trigger a Deep Dream memory distillation cycle")
async def cmd_dream(ctx: GodcmdContext) -> str:
    """Trigger a Deep Dream cycle."""
    from app.core.memory.dream.scheduler import DreamScheduler

    project_id = int(ctx.args[0]) if ctx.args and ctx.args[0].isdigit() else ctx.project_id

    scheduler = DreamScheduler()
    record = await scheduler.run(project_id=project_id)

    if record is None:
        return "Dream skipped: last run too recent (24h cooldown). Use #dream force to override."

    if record.error:
        return f"Dream failed: {record.error}"

    return (f"Dream complete: {record.episodes_count} episodes replayed, "
            f"{record.insights_count} insights generated.")


def register_builtin_commands() -> None:
    """Register all built-in godcmd commands (called at startup)."""
    pass
