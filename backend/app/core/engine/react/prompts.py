"""React engine system-prompt assembly (OpenCode `system.ts` / `request.ts` semantic).

组装单 Agent 人格：
  main.txt 静态层
  + 通道变体（voice / duty 追加段）
  + 动态索引块（<available_skills> / <available_macros> / <available_mcp>）
  + 记忆块（热记忆摘要，冷记忆 recall）
"""

from __future__ import annotations

import logging
import time
from typing import Any

from app.core.context.manager import ContextManager
from app.utils.prompt_loader import prompt_exists, render_prompt

logger = logging.getLogger(__name__)

# 各索引块最多注入的条目数
MAX_SKILLS = 20
MAX_MACROS = 20
MAX_MCP = 10
MAX_AGENTS = 10

#: <available_agents> 远端设备索引的短时缓存（避免每次组装 system prompt 都打网关）
_agents_cache: tuple[float, str | None] = (0.0, None)
_AGENTS_CACHE_TTL = 30.0


async def _available_agents_block() -> str:
    global _agents_cache
    now = time.monotonic()
    if now - _agents_cache[0] < _AGENTS_CACHE_TTL and _agents_cache[1] is not None:
        return _agents_cache[1]
    try:
        from app.core.engine.tools.a2a import list_available_agents

        text = await list_available_agents()
    except Exception as e:
        logger.warning(f"[ReactPrompt] available_agents fetch failed: {e}")
        text = ""
    _agents_cache = (now, text)
    return text or ""


def _environment_block(ctx: Any, state: Any) -> str:
    wd = ctx.working_directory or ""
    lines = [
        f"工作目录: {wd}",
        f"平台: {__import__('platform').platform()}",
    ]
    if ctx.project_id:
        lines.insert(0, f"项目 ID: {ctx.project_id}")
    # 计划状态（若有）
    plan = getattr(state, "structured_plan", None) or getattr(state, "current_plan", None)
    if plan:
        lines.append(f"当前计划: {plan}")
    return "\n".join(lines)


def _capability_index(ctx: Any) -> str:
    parts = []
    metadata = ctx.metadata or {}

    skills = metadata.get("active_skills") or metadata.get("active_skills_index")
    if skills:
        skill_lines = [
            s.strip().lstrip("- ").strip()
            for s in str(skills).splitlines()
            if s.strip()
        ][:MAX_SKILLS]
        parts.append(
            "<available_skills>\n"
            + "\n".join(f"- {s}" for s in skill_lines)
            + "\n</available_skills>"
        )

    macros = metadata.get("active_macros") or metadata.get("active_macros_index")
    if macros:
        macro_lines = [
            m.strip().lstrip("- ").strip()
            for m in str(macros).splitlines()
            if m.strip()
        ][:MAX_MACROS]
        parts.append(
            "<available_macros>\n"
            + "\n".join(f"- {m}" for m in macro_lines)
            + "\n</available_macros>"
        )

    operation_map = metadata.get("operation_map")
    if operation_map:
        parts.append(f"<operation_map>\n{str(operation_map)[:2000]}\n</operation_map>")

    return "\n\n".join(parts) if parts else "（当前无按需加载的能力索引）"


async def _capability_index_async(ctx: Any) -> str:
    """异步版本：在 skills/macros/mcp 索引基础上追加 <available_agents>（A2A 远端设备）。"""
    parts = []
    static = _capability_index(ctx)
    if static and not static.startswith("（当前无"):
        parts.append(static)
    agents = await _available_agents_block()
    if agents:
        parts.append(f"<available_agents>\n{agents[:MAX_AGENTS * 200]}\n</available_agents>")
    return "\n\n".join(parts) if parts else "（当前无按需加载的能力索引）"


def _memory_block(ctx: Any) -> str:
    metadata = ctx.metadata or {}
    hot = metadata.get("core_memory_raw") or metadata.get("hot_memory")
    episodes = metadata.get("episodic_memory_raw")
    block = ""
    if hot:
        block += f"【热记忆】\n{str(hot)[:300]}"
    if episodes:
        block += f"\n【近期剧集】\n{str(episodes)[:500]}"
    return block or "（无热记忆；需要时可调用 remember/recall 查询）"


async def build_system_prompt(state: Any, config: dict[str, Any]) -> str:
    """组装单 Agent system prompt。"""
    ctx = ContextManager.current()

    placeholders = {
        "user_lang": "中文",
        "environment_block": _environment_block(ctx, state),
        "capability_index": await _capability_index_async(ctx),
        "memory_block": _memory_block(ctx),
    }

    # 子代理：使用子代理类型专用人格（对齐 OpenCode 每子代理类型专属 prompt），
    # 且不注入主 Agent 的 main.txt 人格，避免子代理被主 Agent 话术污染。
    meta = config.get("metadata", {}) or {}
    subagent_prompt = (
        getattr(ctx.metadata, "subagent_prompt", None)
        or meta.get("subagent_prompt")
    )
    if subagent_prompt and prompt_exists(subagent_prompt):
        return render_prompt(subagent_prompt, placeholders)

    main = render_prompt("core/agent/main.txt", placeholders)

    # 通道变体（对齐 OpenCode 模型变体思路）
    source = ctx.metadata.source or config.get("metadata", {}).get("source", "")
    if source == "voice" and prompt_exists("core/agent/main.voice.txt"):
        main += "\n\n" + render_prompt("core/agent/main.voice.txt")
    elif source in ("duty", "wecom_duty") and prompt_exists("core/agent/main.duty.txt"):
        main += "\n\n" + render_prompt("core/agent/main.duty.txt")

    return main
