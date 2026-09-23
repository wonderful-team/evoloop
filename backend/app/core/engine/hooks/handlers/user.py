"""
User prompt submission hook handler.
"""

from app.core.engine.hooks.core import HookContext, HookResult
from app.core.routing.command_router import CommandRouter

command_router = CommandRouter()


async def user_prompt_submit_handler(context: HookContext) -> HookResult:
    """
    Process user prompt before it's handled.

    Runs a lightweight L0 intent classification for every user prompt and
    attaches the resulting ``intent_hint`` to the context metadata so the
    downstream hydrator can load context telescopically.  If the caller has
    already supplied an ``intent_hint`` (e.g. from the chat endpoint which runs
    L0 for fast-path local actions), we keep it and skip re-classification.

    Other responsibilities:
    - Prompt validation
    - Command shortcuts
    - Context injection
    """
    prompt = context.metadata.prompt or ""

    # Example: Command shortcuts
    shortcuts = {
        "/remember": "Please extract and save any important information from our conversation.",
        "/summary": "Please provide a summary of what we've accomplished so far.",
        "/compact": "The context is getting long. Please summarize key points and continue.",
    }

    if prompt in shortcuts:
        modified_context = context
        modified_context.metadata.prompt = shortcuts[prompt]
        return HookResult(
            success=True,
            message=f"Expanded shortcut: {prompt}",
            modified_context=modified_context,
        )

    # Reuse an already-computed intent hint if the entry point provided one.
    existing = context.metadata.get("intent_hint")
    if existing:
        return HookResult(success=True, message="intent_hint already provided")

    # 值守唤醒（source=duty）不做兜底域分类：任务域已由 dispatcher 的
    # resolve_wakeup_domain 权威解析（pid=0 fail-open 全量面）。此处再跑 L1
    # 会按措辞猜域，把任务误装进项目受限 profile——2026-09-23 实测事故：
    # Upwork 侦察轮被猜成 ecommerce → 商城 profile 的 native_tools 白名单
    # 裁掉 bash/文件工具，Agent Reach 被域过滤藏出 <available_skills>，
    # Agent 只剩 webfetch/websearch 死循环。
    if context.metadata.get("source") == "duty":
        return HookResult(
            success=True, message="duty wakeup: skip L0 (dispatcher-authoritative)"
        )

    # L0 classification is best-effort; failures must not block the request.
    try:
        decision = await command_router.resolve(
            prompt,
            thread_id=context.thread_id or "",
            project_id=context.project_id or 0,
            source=context.metadata.get("source", "chat"),
            # 兜底分类只做 L1 域分类：L0 模板宏仅服务于 voice 通道的毫秒级截流，
            # 任何文本入口的兜底路径都不得静默执行本地宏。
            skip_l0=True,
        )
    except Exception as exc:  # noqa: BLE001
        return HookResult(
            success=True,
            message=f"L0 classification failed: {exc}",
            data={"intent_hint": None},
        )

    if decision.intent_hint:
        intent_hint_dict = decision.intent_hint.model_dump()
        context.metadata.intent_hint = intent_hint_dict
        return HookResult(
            success=True,
            message="L0 intent_hint attached",
            modified_context=context,
            data={"intent_hint": intent_hint_dict},
        )

    return HookResult(success=True)
