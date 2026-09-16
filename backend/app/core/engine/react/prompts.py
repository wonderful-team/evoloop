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
from pathlib import Path
from typing import Any

from app.core.channel.duty.constants import CUSTOMER_FACING_CHANNEL_NAMES
from app.core.context.manager import ContextManager
from app.utils.prompt_loader import prompt_exists, render_prompt

logger = logging.getLogger(__name__)

# 各索引块最多注入的条目数
# 域裁剪（v3.1）：截断前按 相关性重排——已加载 > 已预挂 > 当前域包 > 其余
# （稳定排序），通用技能增长不再挤掉域内包（v3 曾实测 mall-orders 被
# 硬截断导致预挂标记丢失，当时只能靠抬上限到 40 缓解）。
MAX_SKILLS = 40
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
    # 多租户：呈现容器视角（/workspace），不再泄露宿主真实路径
    from app.core.config import settings as _settings

    wd = ctx.working_directory or ""
    if _settings.MULTI_TENANT_MODE:
        from app.core.engine.react.workspace_view import to_agent_view_path

        wd = to_agent_view_path(wd) or ""
    lines = [
        f"工作目录: {wd}",
    ]
    if not _settings.MULTI_TENANT_MODE:
        lines.append(f"平台: {__import__('platform').platform()}")
    if _settings.MULTI_TENANT_MODE:
        lines.append(
            "运行环境: 隔离容器（仅 /workspace 可用，对应你的专属工作区）。"
            "容器外的宿主机路径、其他用户的目录均不存在也访问不到；"
            "越界命令会直接失败，无需尝试。"
        )
    if ctx.project_id:
        lines.insert(0, f"项目 ID: {ctx.project_id}")
    # 计划状态（若有）
    plan = getattr(state, "structured_plan", None) or getattr(state, "current_plan", None)
    if plan:
        lines.append(f"当前计划: {plan}")
    return "\n".join(lines)


def _capability_index(ctx: Any, domain_pkgs: set[str] | None = None) -> str:
    parts = []
    metadata = ctx.metadata or {}

    skills = metadata.get("active_skills")
    if skills:
        loaded_packages = set(metadata.get("loaded_packages") or [])
        preselected_packages = set(metadata.get("preselected_packages") or [])
        if isinstance(skills, list):
            # 域裁剪（v3.1）：截断前按相关性稳定重排——
            # 已加载 > 已预挂 > 当前域包 > 其余（组内保持原序）。
            def _rank(item: Any) -> int:
                n = getattr(item, "name", "")
                if n in loaded_packages:
                    return 0
                if n in preselected_packages:
                    return 1
                if domain_pkgs and n in domain_pkgs:
                    return 2
                return 3

            ordered = sorted(skills, key=_rank) if skills else []
            dropped = max(0, len(ordered) - MAX_SKILLS)
            ordered = ordered[:MAX_SKILLS]
            # 格式化为索引行，避免 str(list) 的 repr 垃圾进 prompt
            skill_lines = []
            for item in ordered:
                name = getattr(item, "name", None)
                if not name:
                    continue
                desc = (getattr(item, "description", "") or "").replace("\n", " ")
                skill_lines.append(f"{name}: {desc}")
            if dropped:
                skill_lines.append(
                    f"…（另有 {dropped} 项与当前域无关未显示；跨域任务可调用 skill(name) 按需加载）"
                )
        else:
            # legacy 字符串形态（dict/getattr 兼容路径）
            skill_lines = [
                s.strip().lstrip("- ").strip()
                for s in str(skills).splitlines()
                if s.strip()
            ][:MAX_SKILLS]
        # 能力包状态标记（capability-packages-refactor.md §6-#7）：预选包标注
        # 「已预挂」（写工具受 G4 约束），已加载包标注「已加载」（SOP 已读，
        # 全量工具可用）
        marked = []
        for line in skill_lines:
            # 行首即技能/包名（name: desc）——按名字前缀取集合成员判定，
            # 注意 pkg 是集合元素而非集合本身（早期实现曾把 set 当字符串
            # f-string，标记从未生效）
            head = line.split(":", 1)[0].strip()
            if head in preselected_packages:
                line = f"{line} [已预挂（写操作需先加载本包）]"
            elif head in loaded_packages:
                line = f"{line} [已加载，工具可用]"
            marked.append(line)
        parts.append(
            "<available_skills>\n"
            + "\n".join(f"- {s}" for s in marked)
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
    # 域裁剪：取当前域的包名集合（discovery 内存索引 O(1)），供截断排序加权
    domain_pkgs: set[str] | None = None
    try:
        from app.core.learning.skills.discovery import skill_discovery

        hint = (ctx.metadata or {}).get("intent_hint") or {}
        domain = (
            hint.get("domain")
            if isinstance(hint, dict)
            else getattr(hint, "domain", None)
        )
        if domain:
            domain_pkgs = {
                p.name for p in await skill_discovery.get_packages_for_domain(domain)
            } or None
    except Exception:
        logger.warning("[ReactPrompt] domain packages for ranking unavailable", exc_info=True)
    static = _capability_index(ctx, domain_pkgs)
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


def _host_context_block(config: dict[str, Any]) -> str:
    """宿主（Member Center 后台 iframe）页面上下文块。

    数据来自 config["metadata"]["host_context"]（API 层已过滤为 dict）。
    外部输入：字段白名单提取 + 长度截断；结构异常按无上下文处理并记日志，
    绝不因上下文字段破坏对话请求。
    """
    try:
        meta = (config or {}).get("metadata") or {}
        hc = meta.get("host_context")
        logger.info(
            f"[HostContext] metadata keys={sorted(meta.keys())} host_context_type={type(hc).__name__}"
        )
        if not isinstance(hc, dict) or not hc:
            return ""

        route = str(hc.get("route") or "").strip()[:200]
        if not route:
            return ""
        page = str(hc.get("page_name") or hc.get("pageName") or "").strip()[:50]
        entity = hc.get("entity")
        entity_desc = ""
        if isinstance(entity, dict):
            etype = str(entity.get("type") or "").strip()[:30]
            eid = str(entity.get("id") or "").strip()[:64]
            if etype and eid:
                entity_desc = f"当前实体：{etype} #{eid}\n"

        # 审计修复：业务专属话术（商城后台/capability-matrix）此前硬编码在
        # 引擎层，违反「引擎保持通用」约定。引擎只生成通用结构；业务指引
        # （宿主是什么系统、用哪个 MCP server、指代消解规则）由项目级
        # fragment 注入（如 project:.evoloop/fragments/mall_ops.md）。
        lines = [
            "操作员正在宿主系统页面中浏览（你是内嵌在该系统的 AI 助手）：",
            f"当前页面：{page or route}（路由: {route}）",
        ]
        if entity_desc:
            lines.append(entity_desc.strip())
        lines.append(
            "仅当用户的问题与当前页面/实体相关时才结合此上下文；"
            "需要业务数据时优先使用领域工具查询真实数据，不要编造。"
            "用户提及「这个订单/商品/会员」等指代时，默认指向当前实体。"
        )
        return "<host_context>\n" + "\n".join(lines) + "\n</host_context>"
    except Exception as e:
        logger.warning(f"[ReactPrompt] host_context block skipped: {e}")
        return ""


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

    # 域专属规则段（capability profile 声明；project: 前缀 = 项目工作区文件，
    # 域内容归项目侧，引擎保持通用）
    try:
        from app.core.engine.capability_profiles import get_profile

        hint = (config or {}).get("metadata", {}).get("intent_hint") or {}
        domain = hint.get("domain") if isinstance(hint, dict) else getattr(hint, "domain", None)
        wd = ctx.working_directory or ""
        profile = get_profile(domain, wd)
        for fragment in profile.prompt_fragments or []:
            if fragment.startswith("project:"):
                frag_path = Path(wd) / fragment[len("project:"):]
                if wd and frag_path.is_file():
                    main += "\n\n" + frag_path.read_text(encoding="utf-8").strip()
                else:
                    logger.warning(f"[ReactPrompt] project fragment missing: {frag_path}")
            elif prompt_exists(fragment):
                main += "\n\n" + render_prompt(fragment)
    except Exception as e:
        logger.warning(f"[ReactPrompt] domain fragments skipped: {e}")

    # 宿主页面上下文（主 Agent 专属；子代理不注入，避免污染专属人格）
    host_block = _host_context_block(config)
    if host_block:
        main += "\n\n" + host_block

    # 通道变体（对齐 OpenCode 模型变体思路）
    source = ctx.metadata.source or config.get("metadata", {}).get("source", "")
    if source == "voice" and prompt_exists("core/agent/main.voice.txt"):
        main += "\n\n" + render_prompt("core/agent/main.voice.txt")
    elif source in ("duty", "wecom_duty") and prompt_exists("core/agent/main.duty.txt"):
        main += "\n\n" + render_prompt("core/agent/main.duty.txt")
        # autonomous duty: expose channel marker; only customer-facing
        # channels get the hard-limit section (main.duty.customer.txt).
        meta = ctx.metadata if isinstance(ctx.metadata, dict) else {}
        channel_name = meta.get("channel_name") or config.get(
            "metadata", {}
        ).get("channel_name") or ""
        if channel_name in CUSTOMER_FACING_CHANNEL_NAMES:
            main += '\n\n<duty_channel customer_facing="true" />'
            if prompt_exists("core/agent/main.duty.customer.txt"):
                main += (
                    "\n\n"
                    + render_prompt("core/agent/main.duty.customer.txt")
                )
        else:
            main += '\n\n<duty_channel customer_facing="false" />'

    return main
