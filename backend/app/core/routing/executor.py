"""Execution + result pushback for routed voice decisions (design §16).

- ``skill`` / deterministic: ``SkillExecutionService`` (preflight gates +
  ``run_deterministic`` under ``VOICE_POLICY`` — no self-heal, desktop-only
  sources) → push ``voice.route_result(done|failed)`` synchronously (short,
  no finish hook).
- ``skill`` / agentic and ``agent``: ``dispatch_agent_run`` + ``run_agent_background``;
  the terminal ``done|failed`` is pushed by ``VoiceChannel`` (handles
  ``SessionCompletedEvent`` / ``AgentRunCompletedEvent`` via ``UniversalBridgeSubscriber``,
  filtered by ``source == "voice"``). Local targets are a no-op here (the client
  already executed them, §8.2).

Default policy (§16.5): deterministic failure does NOT fall back to agentic;
voice skills only allow DESKTOP macros (DOM/MOBILE → ``failed``).
"""

from __future__ import annotations

import asyncio
import json
import logging
from contextvars import ContextVar
from typing import Any

from app.core.routing._errors import ROUTE_EXCEPTIONS
from app.core.routing.connection import manager
from app.core.routing.schemas import RouteDecision
from app.core.schemas.canonical import MessageType, create_envelope
from app.infrastructure.database import session_scope
from app.models.macro import Macro
from app.utils.parameters import missing_required_params

logger = logging.getLogger(__name__)

# thread_id -> "skill" | "agent". Authoritative voice-source marker consumed by
# VoiceChannel to push the terminal result. In-memory only: a restart
# mid-run loses it, but the WS is gone too, so the client's 60s timeout covers
# it (§9.2).
_voice_registry: dict[str, str] = {}
_voice_lock = asyncio.Lock()

# message_id carrier for terminal-result caching of duplicate route requests.
_current_message_id: ContextVar[str | None] = ContextVar(
    "_current_message_id", default=None
)


async def _mark_voice(thread_id: str, kind: str) -> None:
    async with _voice_lock:
        _voice_registry[thread_id] = kind


async def consume_voice(thread_id: str) -> str | None:
    """Pop and return the voice-source kind for `thread_id` (finish.py hook)."""
    async with _voice_lock:
        return _voice_registry.pop(thread_id, None)


async def push_voice_result(thread_id: str, status: str, summary: str) -> None:
    body = {
        "thread_id": thread_id,
        "status": status,
        "summary": summary,
    }
    await manager.push(thread_id, create_envelope(
        MessageType.VOICE_ROUTE_RESULT, body
    ).model_dump())
    message_id = _current_message_id.get()
    if message_id:
        await manager.record_terminal_result(message_id, body)


# ---------------------------------------------------------------------------
# VoiceTaskRegistry — register / cancel active voice tasks per thread
# ---------------------------------------------------------------------------

_voice_tasks: dict[str, asyncio.Task[Any]] = {}
_voice_task_lock = asyncio.Lock()

# Per-thread locks to prevent overlapping route execution (barge-in safety).
_thread_locks: dict[str, asyncio.Lock] = {}
_thread_locks_lock = asyncio.Lock()


async def get_thread_lock(thread_id: str) -> asyncio.Lock:
    async with _thread_locks_lock:
        if thread_id not in _thread_locks:
            _thread_locks[thread_id] = asyncio.Lock()
        return _thread_locks[thread_id]


async def register_voice_task(thread_id: str, task: asyncio.Task[Any]) -> None:
    async with _voice_task_lock:
        old = _voice_tasks.get(thread_id)
        if old is not None and not old.done():
            old.cancel()
        _voice_tasks[thread_id] = task


async def cancel_voice_task(thread_id: str) -> bool:
    async with _voice_task_lock:
        task = _voice_tasks.pop(thread_id, None)
    if task is not None and not task.done():
        task.cancel()
        logger.info("[voice-executor] cancelled task for thread %s", thread_id)
        return True
    return False


# ---------------------------------------------------------------------------
# Streaming LLM output — token-by-token push via voice.token / voice.tts_boundary
# ---------------------------------------------------------------------------

_SENTENCE_BOUNDARIES = "。！？.!?\n…"


async def push_voice_token(thread_id: str, token: str, index: int) -> None:
    await manager.push(thread_id, create_envelope(
        MessageType.VOICE_TOKEN,
        {"thread_id": thread_id, "token": token, "index": index},
    ).model_dump())


async def push_voice_tts_boundary(thread_id: str, sentence: str, index: int) -> None:
    await manager.push(thread_id, create_envelope(
        MessageType.VOICE_TTS_BOUNDARY,
        {"thread_id": thread_id, "sentence": sentence, "index": index},
    ).model_dump())


async def stream_llm_response(
    thread_id: str,
    messages: list[dict],
    model_name: str,
    *,
    temperature: float = 0.7,
    max_tokens: int = 1024,
    base_url: str | None = None,
    api_key: str | None = None,
) -> str:
    """Stream LLM output token-by-token, pushing voice.token and voice.tts_boundary.

    Returns the full accumulated text.
    Cancels gracefully if the task is cancelled (barge-in).
    """
    from app.infrastructure.llm.factory import LLMConfig, LLMFactory

    config = LLMConfig(
        model_name=model_name,
        temperature=temperature,
        max_tokens=max_tokens,
        streaming=True,
        base_url=base_url,
        api_key=api_key,
    )
    llm = await LLMFactory.create_llm(config)

    token_index = 0
    sentence_buf = ""
    full_text = ""

    try:
        async for chunk in llm.astream(messages, config={"callbacks": []}):
            token = getattr(chunk, "content", "") or ""
            if not token:
                continue
            full_text += token
            sentence_buf += token
            await push_voice_token(thread_id, token, token_index)
            token_index += 1

            if any(ch in _SENTENCE_BOUNDARIES for ch in token):
                stripped = sentence_buf.strip()
                if stripped:
                    await push_voice_tts_boundary(thread_id, stripped, token_index)
                sentence_buf = ""

        if sentence_buf.strip():
            await push_voice_tts_boundary(thread_id, sentence_buf.strip(), token_index)

    except asyncio.CancelledError:
        logger.info("[voice-executor] LLM stream cancelled for thread %s", thread_id)
        raise
    except (ValueError, OSError, RuntimeError, TypeError, KeyError, AttributeError) as exc:
        logger.error("[voice-executor] LLM stream failed: %s", exc)
        raise

    return full_text


async def _run_skill(thread_id: str, decision: RouteDecision) -> None:
    from app.constants import DEFAULT_PROJECT_ID
    from app.core.execution.macro.runner import (
        VOICE_POLICY,
        MacroGateError,
        preflight,
        run_deterministic,
    )
    from app.models.learning import LearnedSkill

    skill_id = decision.target.get("id")
    if skill_id is None:
        await push_voice_result(thread_id, "failed", "skill id missing")
        return

    async with session_scope() as session:
        skill = await session.get(LearnedSkill, skill_id)
        if skill is None:
            await push_voice_result(thread_id, "failed", f"skill #{skill_id} not found")
            return

        skill_name = skill.name
        skill_description = skill.description or ""
        macro = None
        if skill.macro_id:
            macro = await session.get(Macro, skill.macro_id)

    if macro is not None:
        try:
            script = preflight(macro, decision.params or {})
        except MacroGateError as e:
            await push_voice_result(thread_id, "failed", e.message)
            return

        outcome = await run_deterministic(
            macro,
            thread_id=thread_id,
            params=decision.params or {},
            project_id=DEFAULT_PROJECT_ID,
            script=script,
            policy=VOICE_POLICY,
            skill_name=skill_name,
        )
        await push_voice_result(
            thread_id,
            "done" if outcome.ok else "failed",
            outcome.message or (f"已完成{skill_name}" if outcome.ok else "处理失败"),
        )
        return

    # Param gate must run before the mode branch, matching REST execute.
    missing = missing_required_params(skill.parameters, decision.params or {})
    if missing:
        await push_voice_result(
            thread_id, "failed", f"Missing required parameters: {', '.join(missing)}"
        )
        return

    # Agentic skill: hand to the agent graph; terminal result via finish hook.
    directive = (
        decision.params.get("task") or skill_description or skill_name
    )
    await _run_agent(
        thread_id,
        message_content=f"[Skill: {skill_name}] {directive}",
        project_id=DEFAULT_PROJECT_ID,
        metadata={
            "source": "voice",
            "voice_thread_id": thread_id,
            "original_skill_id": skill_id,
        },
        kind="skill",
    )


def _update_session_frame(
    thread_id: str, script: Any, params: dict, extracted: dict, macro_id: int
) -> None:
    """Record where the browser is and what we just talked about, so the
    NEXT utterance in this conversation can resolve anaphora (它/这个) and
    the engine can skip redundant navigation. Frame is conversation-scoped.
    """
    from app.core.routing import session_frame

    values = {**{k: v for k, v in extracted.items() if v is not None}, **params}
    last_nav: str | None = None
    for step in script.steps:
        if step.event_type != "navigate":
            continue
        url = (step.payload or {}).get("url")
        if not isinstance(url, str):
            continue
        for k, v in values.items():
            url = url.replace("{{" + str(k) + "}}", str(v))
        if "{{" not in url:
            last_nav = url

    entity = None
    if params.get("query") or extracted.get("entity_id") or extracted.get("value") is not None:
        entity = {
            "query": params.get("query"),
            "entity_id": extracted.get("entity_id"),
            "value": extracted.get("value"),
            "macro_id": macro_id,
        }
    session_frame.update_frame(thread_id, current_page=last_nav, current_entity=entity)


async def _run_macro(thread_id: str, decision: RouteDecision) -> dict | None:
    """Execute a routed macro under VOICE_POLICY (mirrors _run_skill's
    deterministic branch, loading from the independent macros table).

    Returns the extracted_data on success (feeds multi-intent chains);
    None on any failure or delegation path.
    """
    from app.core.execution.macro import lifecycle
    from app.core.execution.macro.runner import (
        VOICE_POLICY,
        _collect_sources,
        _scan_steps_risk,
    )
    from app.core.execution.macro.schemas import RISK_TIER_ORDER, MacroScript
    from app.utils.yaml import YAMLError

    macro_id = decision.target.get("id")
    if macro_id is None:
        await push_voice_result(thread_id, "failed", "macro id missing")
        return None

    macro = await lifecycle.load_macro(int(macro_id))
    if macro is None:
        await push_voice_result(thread_id, "failed", f"macro #{macro_id} not found")
        return None
    if not macro.is_routable():
        await push_voice_result(
            thread_id, "failed", f"宏 #{macro_id} 未确认，请先在宏库中确认"
        )
        return None

    missing = missing_required_params(macro.parameters, decision.params or {})
    if missing:
        if "query" in missing:
            # Ask instead of failing: store the utterance as pending; the
            # user's next sentence ("夜光亚克力钥匙扣") is spliced back in.
            from app.core.routing import session_frame

            text = (decision.params or {}).get("_text") or macro.name
            question = session_frame.clarify_question(text)
            session_frame.update_frame(
                thread_id, pending={"kind": "missing_entity", "text": text}
            )
            await push_voice_result(thread_id, "clarify", question)
        else:
            await push_voice_result(
                thread_id, "failed", f"缺少参数: {', '.join(missing)}"
            )
        return None

    try:
        script = MacroScript.from_yaml(macro.macro_script)
    except (ValueError, OSError, RuntimeError, TypeError, KeyError, YAMLError) as e:
        await push_voice_result(thread_id, "failed", f"宏脚本解析失败: {e}")
        return None

    if VOICE_POLICY.allowed_sources is not None:
        sources = _collect_sources(script.steps)
        unsupported = sources - VOICE_POLICY.allowed_sources
        if sources and unsupported:
            await push_voice_result(
                thread_id,
                "failed",
                f"unsupported macro source for voice: {sorted(unsupported)}",
            )
            return None
    reason = _scan_steps_risk(script.steps, VOICE_POLICY)
    if reason:
        await push_voice_result(thread_id, "failed", f"policy gate rejected: {reason}")
        return None

    # ── Metadata-level risk gate (before YAML parse overhead) ───────────────
    # Compare macro.risk_tier directly against VOICE_POLICY.max_risk_tier.
    # This catches high-risk macros even when individual steps appear safe,
    # and avoids unnecessary YAML parsing for macros that would be blocked anyway.
    if VOICE_POLICY.max_risk_tier is not None:
        meta_risk = macro.risk_tier or "observe"
        if RISK_TIER_ORDER.get(meta_risk, 0) > RISK_TIER_ORDER.get(
            VOICE_POLICY.max_risk_tier, 0
        ):
            # money / escape tier: don't hard-block. Delegate to Agent for
            # multi-turn voice confirmation (HITL 降级模式 §16.5).
            from app.constants import DEFAULT_PROJECT_ID

            task = decision.params.get("task", "") or decision.raw or macro.name
            logger.info(
                "[voice-executor] macro #%s risk_tier=%s exceeds policy max=%s; "
                "delegating to agent for HITL confirmation",
                macro.id,
                meta_risk,
                VOICE_POLICY.max_risk_tier,
            )
            await _run_agent(
                thread_id,
                message_content=(
                    f"[Macro: {macro.name}] {task}\n"
                    f"(这是一个 {meta_risk} 级宏，执行前请向用户确认操作的具体内容和风险。)"
                ),
                project_id=DEFAULT_PROJECT_ID,
                metadata={
                    "source": "voice",
                    "voice_thread_id": thread_id,
                    "macro_id": macro.id,
                    "macro_risk_tier": meta_risk,
                    "requires_hitl": True,
                },
                kind="macro",
            )
            return None

    from app.core.execution.macro.engine import MacroEngine

    # Frame probe (cheap insurance): if the browser is NOT where the frame
    # thinks it is, the user touched the page mid-conversation — distrust the
    # whole frame (entity included) rather than act on a stale referent.
    from app.core.routing import session_frame

    frame = session_frame.get_frame(thread_id)
    if frame is not None and frame.current_page:
        from playwright.async_api import Error as PlaywrightError

        from app.infrastructure.drivers.browser import browser_manager

        try:
            page = await browser_manager.get_page(thread_id=thread_id)
            actual = page.url if page else None
        except (PlaywrightError, OSError, RuntimeError, ValueError):
            actual = None
        if actual and actual.rstrip("/") != frame.current_page.rstrip("/"):
            logger.info(
                "[voice-executor] frame probe mismatch: frame=%s actual=%s -> clear",
                frame.current_page,
                actual,
            )
            session_frame.clear_frame(thread_id)

    params = dict(decision.params or {})
    params["_macro_id"] = macro.id
    params["_macro_name"] = macro.name
    extracted: dict[str, Any] = {}
    ok, msg, data = await MacroEngine.execute(
        thread_id, script, params=params, extracted_data=extracted
    )
    if ok:
        # Empty summary must not stay empty: the client speaks nothing for
        # done+"" and the user is left hanging after "请稍后" (native macros
        # return no engine message). Fall back to the macro's leaf name.
        await push_voice_result(
            thread_id, "done", msg or f"已完成{macro.name.rsplit('>', 1)[-1].strip()}"
        )
        _update_session_frame(thread_id, script, params, extracted, macro.id)
        return extracted

    # Align with MacroService's failure path: the agent relay IS self-healing,
    # so it must respect the same policy gates (global / execution-level).
    # The macros table has no skill-level switch — skill=None checks the rest.
    from app.core.execution.macro.healing_policy import SelfHealingPolicy

    healing = SelfHealingPolicy.check(macro=None, execution_params=params)
    if not healing.allowed:
        await push_voice_result(
            thread_id, "failed", f"{msg}（自愈已禁用：{healing.reason}）"
        )
        return None
    await _relay_macro_failure(thread_id, decision, macro, msg, data, extracted)
    return None


async def _relay_macro_failure(
    thread_id: str,
    decision: RouteDecision,
    macro,
    error_msg: str,
    failure_data: dict[str, Any] | None,
    extracted: dict[str, Any],
) -> None:
    """Macro execution failed -> hand the original intent to the Agent with a
    failure brief (failed step, error, partial extractions, screenshot).

    The Agent can retry differently, fall back to GUI operation, or ask the
    user; its terminal result is delivered via the finish hook, so no
    push_voice_result("failed") is sent here. Policy-gate rejections upstream
    never reach this path — relay only covers EXECUTION failure.
    """
    from app.constants import DEFAULT_PROJECT_ID

    task = decision.params.get("task", "") or decision.raw or macro.name
    data = failure_data or {}
    step_no = data.get("step_number")
    event_type = data.get("event_type")
    screenshot = data.get("screenshot_path")

    brief_lines = [
        "[宏执行失败，请接力完成用户意图]",
        f"用户原始指令：{task}",
        f"宏：{macro.name}（#{macro.id}）",
    ]
    if step_no is not None:
        brief_lines.append(f"失败位置：第 {step_no} 步（{event_type}）")
    brief_lines.append(f"失败原因：{(error_msg or '未知')[:300]}")
    if extracted:
        brief_lines.append(
            f"宏已提取的数据：{json.dumps(extracted, ensure_ascii=False)[:500]}"
        )
    if screenshot:
        brief_lines.append(f"失败截图：{screenshot}")
    brief_lines.append(
        "请换用其他方式完成用户意图（可改用 GUI 操作、调整参数重试，"
        "或向用户确认后放弃），完成后正常汇报结果。"
    )

    logger.info(
        "[voice-executor] macro #%s failed at step %s; relaying to agent",
        macro.id,
        step_no,
    )
    await _run_agent(
        thread_id,
        message_content="\n".join(brief_lines),
        project_id=DEFAULT_PROJECT_ID,
        metadata={
            "source": "voice",
            "voice_thread_id": thread_id,
            "macro_id": macro.id,
            "macro_relay": "execution_failure",
            "failed_step": step_no,
        },
        kind="macro",
    )


async def _run_agent(
    thread_id: str,
    message_content: str,
    project_id: int,
    metadata: dict[str, Any],
    kind: str,
) -> None:
    from app.core.engine.background_agent import run_agent_background
    from app.core.engine.dispatch import dispatch_agent_run

    await _mark_voice(thread_id, kind)
    result = await dispatch_agent_run(
        thread_id=thread_id,
        message_content=message_content,
        project_id=project_id,
        metadata=metadata,
    )
    if result.status == "failed":
        await consume_voice(thread_id)
        await push_voice_result(
            thread_id, "failed", getattr(result, "error", "") or "dispatch failed"
        )
        return
    asyncio.create_task(run_agent_background(thread_id, result.inputs))


async def execute(thread_id: str, decision: RouteDecision) -> dict | None:
    """Execute a routed decision and push the terminal voice.route_result.

    Called via ``asyncio.create_task`` from voice_ws, so branches may await
    without blocking the WS read loop. Returns macro extracted_data on
    success (multi-intent chaining); None otherwise.
    """
    try:
        if decision.target_type == "skill":
            return await _run_skill(thread_id, decision)
        elif decision.target_type == "macro":
            return await _run_macro(thread_id, decision)
        elif decision.target_type == "agent":
            from app.constants import DEFAULT_PROJECT_ID

            task = decision.params.get("task", "") or decision.raw or ""
            await _run_agent(
                thread_id,
                message_content=task,
                project_id=DEFAULT_PROJECT_ID,
                metadata={"source": "voice", "voice_thread_id": thread_id},
                kind="agent",
            )
        # local: server does not execute; client already handled it (§8.2).
    except ROUTE_EXCEPTIONS as exc:
        logger.warning("[voice-executor] route execution failed: %s", exc)
        await push_voice_result(thread_id, "failed", str(exc)[:200])
    except (ValueError, OSError, RuntimeError, TypeError, KeyError) as exc:
        logger.warning("[voice-executor] unexpected failure: %s", exc)
        await push_voice_result(thread_id, "failed", str(exc)[:200])
    return None


