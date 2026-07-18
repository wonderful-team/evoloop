"""Single-shot LLM router for the voice channel (bypasses the Agent loop).

Prefers LM Studio's native OpenAI-style tool-calling (`tool_choice="required"`)
and falls back to parsing a Hermes `<tool_call>` / JSON blob. Any parse or
validation failure resolves to `delegate(task=<original text>)`; the router
never raises to the caller.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
from typing import Any

from app.core.routing import init_spec
from app.core.routing._errors import ROUTE_EXCEPTIONS
from app.core.routing.local_matcher import LocalMatcher
from app.core.routing.schemas import RouteCandidate, RouteDecision, RouteRequest
from app.infrastructure.config import SystemConfigService

logger = logging.getLogger(__name__)

_LOCAL_MATCHER: LocalMatcher | None = None
_LOCAL_MATCHER_LOCK = asyncio.Lock()

try:
    from jinja2 import TemplateError as _JinjaTemplateError
except ImportError:  # pragma: no cover - jinja2 is a hard dependency
    _JinjaTemplateError = None

_TEMPLATE_EXCEPTIONS: tuple[type[BaseException], ...] = tuple(
    list(ROUTE_EXCEPTIONS) + ([_JinjaTemplateError] if _JinjaTemplateError else [])
)


async def _get_local_matcher() -> LocalMatcher:
    """Lazily build the deterministic Layer-0 matcher used by the client."""
    global _LOCAL_MATCHER
    if _LOCAL_MATCHER is not None:
        return _LOCAL_MATCHER
    async with _LOCAL_MATCHER_LOCK:
        if _LOCAL_MATCHER is not None:
            return _LOCAL_MATCHER
        spec = await asyncio.to_thread(init_spec.build_init_spec)
        _LOCAL_MATCHER = LocalMatcher(
            templates=spec.templates,
            slot_dictionaries=spec.slot_dictionaries,
            aliases=spec.aliases,
            app_usage_rank=spec.app_usage_rank,
        )
        logger.debug("[router] local matcher initialized")
    return _LOCAL_MATCHER


ROUTE_TOOLS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "execute_skill",
            "description": "Execute a backend learned skill by id with extracted params.",
            "parameters": {
                "type": "object",
                "properties": {
                    "skill_id": {"type": "integer"},
                    "params": {"type": "object"},
                },
                "required": ["skill_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "execute_macro",
            "description": "Execute a deterministic macro script by id with extracted params.",
            "parameters": {
                "type": "object",
                "properties": {
                    "macro_id": {"type": "integer"},
                    "params": {"type": "object"},
                },
                "required": ["macro_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "local_action",
            "description": "Run a deterministic local action on the user's device.",
            "parameters": {
                "type": "object",
                "properties": {
                    "action": {"type": "string"},
                    "params": {"type": "object"},
                },
                "required": ["action"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "delegate",
            "description": "Hand the task to the Evoloop Agent when no skill/local action fits.",
            "parameters": {
                "type": "object",
                "properties": {"task": {"type": "string"}},
                "required": ["task"],
            },
        },
    },
]


def _cfg(key: str, default: str | None = None) -> str | None:
    try:
        return SystemConfigService.get_value(key, default)
    except (ValueError, OSError, RuntimeError, TypeError, KeyError):
        return default


def _min_score() -> float:
    # Score gate for the early-delegate shortcut. Measured on this corpus
    # (bge-base-zh, 34 entries): correct rank-1 scores range 0.31 down to
    # -0.21 (long entity names / colloquial phrasings), while junk queries
    # overlap the SAME band ("帮我写个周报" -0.214, "讲个笑话" -0.035!).
    # No threshold separates them — the embedding only ORDERS candidates;
    # the route LLM is the only competent accept/reject filter. Default
    # -1.0 therefore consults the LLM whenever anything was retrieved;
    # early delegate remains only for an empty candidate list. Set
    # ROUTE_MIN_SCORE higher to trade correctness for latency.
    raw = _cfg("ROUTE_MIN_SCORE", "-1.0")
    try:
        return float(raw) if raw is not None else 0.55
    except (TypeError, ValueError):
        return 0.55


def _top_k() -> int:
    raw = _cfg("ROUTE_TOP_K", "6")
    try:
        return int(raw) if raw is not None else 6
    except (TypeError, ValueError):
        return 6


_MAX_PROMPT_CHARS = 1500
_MAX_CANDIDATE_DESCRIPTION_CHARS = 100
_MAX_CANDIDATE_SCHEMA_CHARS = 100


async def _create_route_llm():
    from app.infrastructure.llm.lightning import get_lightning_service

    service = get_lightning_service()
    llm = await service.get_llm()
    if llm is None:
        raise RuntimeError(
            "Lightning Channel not available. "
            "Set LIGHTNING_MODE to 'llama.cpp', 'lm-studio', or 'ollama' "
            "to enable local route LLM."
        )
    return llm


def _compact_schema(schema: dict[str, Any]) -> str:
    """Return a tiny JSON representation of the schema for the prompt.

    Keeps only the outer property names and their `type` (or `description`
    truncated) to keep tokens low while still letting the LLM know valid
    parameter keys.
    """
    out: dict[str, Any] = {}
    for key, value in schema.items():
        if isinstance(value, dict):
            out[key] = value.get("type") or value.get("description", "")[:40]
        else:
            out[key] = value
    compact = json.dumps(out, ensure_ascii=False, separators=(",", ":"))
    if len(compact) > _MAX_CANDIDATE_SCHEMA_CHARS:
        compact = compact[: _MAX_CANDIDATE_SCHEMA_CHARS - 3] + "..."
    return compact


def _truncate_candidate(c: RouteCandidate) -> dict[str, Any]:
    description = c.description
    if len(description) > _MAX_CANDIDATE_DESCRIPTION_CHARS:
        description = description[: _MAX_CANDIDATE_DESCRIPTION_CHARS - 3] + "..."
    return {
        "id": c.id,
        "type": c.type,
        "name": c.name,
        "description": description,
        "params_schema": _compact_schema(c.params_schema),
    }


def _render_prompt(text: str, candidates: list[RouteCandidate]) -> str:
    cands = [_truncate_candidate(c) for c in candidates]
    try:
        from app.utils.template import render_template

        # Compact template keeps the route LLM prompt small enough for 8k/4k
        # context models used by the voice router.
        rendered = render_template(
            "core/routing/route_compact.prompt.j2", text=text, candidates=cands
        )
    except _TEMPLATE_EXCEPTIONS as exc:
        logger.debug("[router] compact template render fallback: %s", exc)
        rendered = (
            "你是语音助理路由器。根据用户文本与候选，调用一个工具：\n"
            "execute_macro(macro_id, params) / delegate(task)。\n"
            "只能选候选里的 macro_id，否则 delegate。参数从用户文本抽取。\n\n"
            f"用户文本：{text}\n候选：{json.dumps(cands, ensure_ascii=False)}"
        )

    # If the prompt still exceeds the budget, progressively drop the lowest-ranked
    # candidates until it fits. The first candidate is the most likely match.
    while len(rendered) > _MAX_PROMPT_CHARS and len(cands) > 1:
        cands.pop()
        try:
            rendered = render_template(
                "core/routing/route_compact.prompt.j2", text=text, candidates=cands
            )
        except _TEMPLATE_EXCEPTIONS as exc:
            logger.debug("[router] compact template render fallback: %s", exc)
            rendered = (
                "你是语音助理路由器。根据用户文本与候选，调用一个工具：\n"
                "execute_macro(macro_id, params) / delegate(task)。\n"
                "只能选候选里的 macro_id，否则 delegate。参数从用户文本抽取。\n\n"
                f"用户文本：{text}\n候选：{json.dumps(cands, ensure_ascii=False)}"
            )
    logger.debug(
        "[router] prompt rendered: chars=%d candidates=%d", len(rendered), len(cands)
    )
    return rendered


def _delegate(text: str, raw: str | None = None) -> RouteDecision:
    # Per design §8.2 a miss is still reported as status="routed" with
    # target.type="agent"; "delegate" is the target kind, not the frame status.
    # The client Dispatcher only acts on status in {routed, done, failed}, so a
    # distinct "delegate" status would be silently dropped.
    return RouteDecision(
        status="routed",
        target_type="agent",
        target={"type": "agent", "id": "default"},
        params={"task": text},
        raw=raw,
    )


def _candidate_ids(candidates: list[RouteCandidate]) -> set[str]:
    return {c.id for c in candidates}


def _from_tool_call(
    name: str, args: dict[str, Any], ids: set[str], req: RouteRequest, raw: str | None
) -> RouteDecision:
    if name == "execute_skill":
        skill_id = args.get("skill_id")
        cid = f"skill:{skill_id}"
        if cid not in ids:
            logger.info("[router] hallucinated skill_id=%s -> delegate", skill_id)
            return _delegate(req.text, raw)
        return RouteDecision(
            status="routed",
            target_type="skill",
            target={"type": "skill", "id": skill_id},
            params=args.get("params") or {},
            raw=raw,
        )
    if name == "execute_macro":
        macro_id = args.get("macro_id")
        cid = f"macro:{macro_id}"
        if cid not in ids:
            logger.info("[router] hallucinated macro_id=%s -> delegate", macro_id)
            return _delegate(req.text, raw)
        return RouteDecision(
            status="routed",
            target_type="macro",
            target={"type": "macro", "id": macro_id},
            params=args.get("params") or {},
            raw=raw,
        )
    if name == "local_action":
        action = args.get("action")
        cid = f"local:{action}"
        if cid not in ids:
            logger.info("[router] unknown local action=%s -> delegate", action)
            return _delegate(req.text, raw)
        return RouteDecision(
            status="routed",
            target_type="local",
            target={"type": "local", "id": action},
            params=args.get("params") or {},
            raw=raw,
        )
    # default / delegate
    return _delegate(args.get("task") or req.text, raw)


_HERMES_RE = re.compile(r"<tool_call>\s*(\{.*?\})\s*</tool_call>", re.DOTALL)


def _fallback_parse(content: str, ids: set[str], req: RouteRequest) -> RouteDecision:
    """Best-effort Hermes / JSON parse; anything unparseable -> delegate."""
    text = (content or "").strip()
    m = _HERMES_RE.search(text)
    blob = m.group(1) if m else text
    try:
        obj = json.loads(blob)
    except (ValueError, TypeError):
        return _delegate(req.text, content)
    name = obj.get("name") or obj.get("tool")
    args = obj.get("arguments") or obj.get("params") or {}
    if not isinstance(args, dict):
        args = {}
    if name in ("execute_skill", "execute_macro", "local_action", "delegate"):
        return _from_tool_call(name, args, ids, req, content)
    return _delegate(req.text, content)


async def route(req: RouteRequest, candidates: list[RouteCandidate]) -> RouteDecision:
    """Produce a `RouteDecision`. Never raises to the caller."""
    ids = _candidate_ids(candidates)

    # Early delegate when retrieval has no confident match.
    if not candidates or candidates[0].score < _min_score():
        logger.info(
            "[router] early delegate (top score %.3f, candidates=%d)",
            candidates[0].score if candidates else 0.0,
            len(candidates),
        )
        decision = _delegate(req.text)
        decision.candidates = candidates
        return decision

    prompt = _render_prompt(req.text, candidates)
    raw: str | None = None
    try:
        llm = await _create_route_llm()
        runnable = llm.bind_tools(ROUTE_TOOLS, tool_choice="required")
        # AdaptiveChatOpenAI (the production wrapper) requires a messages list;
        # a bare string only works on langchain ChatOpenAI. A list-of-dict works
        # for both.
        ai_msg = await runnable.ainvoke([{"role": "user", "content": prompt}])
        raw = getattr(ai_msg, "content", None)
        tool_calls = getattr(ai_msg, "tool_calls", None) or []
        if tool_calls:
            tc = tool_calls[0]
            name = tc.get("name")
            args = tc.get("args") or {}
            # AdaptiveChatOpenAI returns tool args as a JSON string; langchain
            # returns a dict. Normalize to dict for the downstream validators.
            if isinstance(args, str):
                try:
                    args = json.loads(args)
                except (ValueError, TypeError):
                    args = {}
            if not isinstance(args, dict):
                args = {}
            decision = _from_tool_call(name, args, ids, req, raw)
        else:
            decision = _fallback_parse(raw or "", ids, req)
    except ROUTE_EXCEPTIONS as exc:
        logger.warning("[router] LLM route failed: %s -> delegate", exc)
        decision = _delegate(req.text, raw)

    decision.candidates = candidates
    if decision.target_type == "macro":
        params = dict(decision.params or {})
        params.setdefault("_text", req.text)
        decision.params = params
    return decision


async def route_many(
    req: RouteRequest, candidates: list[RouteCandidate]
) -> list[RouteDecision]:
    """Multi-intent entry: decompose -> route each intent independently.

    Single-intent text (the common case) is byte-identical to today's path.
    For compound instructions each sub-intent gets its OWN retrieval (clean
    embedding per intent) and its own single-shot route; dependency markers
    ride along in decision params (_depends_on / _param_exprs) for the
    executor's resolver stage.
    """
    from app.core.routing import decompose, retriever, session_frame

    frame = session_frame.get_frame(req.thread_id) if req.thread_id else None

    # Frame probe BEFORE anaphora resolution: if the browser is not where the
    # frame thinks it is, the user touched the page mid-conversation — the
    # referent is untrustworthy. Only runs when a prior macro execution set
    # current_page (so the browser is certainly already running).
    if frame is not None and frame.current_page:
        from playwright.async_api import Error as PlaywrightError

        from app.infrastructure.drivers.browser import browser_manager

        try:
            page = await browser_manager.get_page(thread_id=req.thread_id)
            actual = page.url if page else None
        except (PlaywrightError, OSError, RuntimeError, ValueError):
            actual = None
        if actual and actual.rstrip("/") != frame.current_page.rstrip("/"):
            logger.info(
                "[router] frame probe mismatch: frame=%s actual=%s -> clear",
                frame.current_page,
                actual,
            )
            session_frame.clear_frame(req.thread_id)
            frame = None

    # Clarify resume: the previous turn asked "which one?" — this utterance
    # is the answer; splice it into the pending text and re-route.
    text, resumed = session_frame.consume_pending(req.text, frame)
    if resumed:
        logger.info("[router] clarify resume: %s -> %s", req.text, text)
        req = RouteRequest(
            text=text, thread_id=req.thread_id, message_id=req.message_id
        )
        candidates = await retriever.retrieve(text, top_k=_top_k())

    # Clarify trigger: anaphora with no frame entity — asking is cheaper and
    # safer than routing '它的' into a garbage query. Single-clause only:
    # a connector means the entity is named in ANOTHER clause of the same
    # utterance ('查X，然后把它…') — decompose resolves that internally.
    if (
        not resumed
        and (frame is None or not frame.current_entity)
        and session_frame.has_anaphora(req.text)
        and not session_frame.has_connector(req.text)
        and req.thread_id
    ):
        question = session_frame.clarify_question(req.text)
        session_frame.update_frame(
            req.thread_id,
            pending={"kind": "missing_entity", "text": req.text},
        )
        logger.info("[router] clarify ask: %s (pending=%s)", question, req.text)
        return [
            RouteDecision(
                status="clarify",
                target_type="clarify",
                target={"type": "clarify"},
                params={"question": question},
                raw=None,
            )
        ]

    # Cross-turn anaphora: rewrite BEFORE decompose and retrieval so the
    # embedding and the LLM both see a self-contained utterance.
    rewritten = session_frame.resolve_anaphora(req.text, frame)
    if rewritten != req.text:
        logger.info("[router] anaphora rewrite: %s -> %s", req.text, rewritten)
        req = RouteRequest(
            text=rewritten, thread_id=req.thread_id, message_id=req.message_id
        )
        candidates = await retriever.retrieve(rewritten, top_k=_top_k())

    # Context switch: phrases like "那换成查X" mean the user is abandoning the
    # current frame entity and starting a new one. Drop the frame and normalize.
    normalized, switched = session_frame.normalize_context_switch(req.text)
    if switched:
        logger.info("[router] context switch: %s -> %s", req.text, normalized)
        if frame is not None:
            session_frame.clear_frame(req.thread_id)
            frame = None
        req = RouteRequest(
            text=normalized, thread_id=req.thread_id, message_id=req.message_id
        )
        candidates = await retriever.retrieve(normalized, top_k=_top_k())

    # Layer-0 deterministic short-circuit: if the client's LocalMatcher would
    # have handled the utterance, route it to local_action before any LLM or
    # multi-intent decomposition can misclassify it (e.g. "音量大一点" ->
    # local set_volume instead of a volume-adjust macro). Compound commands
    # anchored-match will fail and continue down the LLM path.
    matcher = await _get_local_matcher()
    local_hit = matcher.match(req.text)
    if local_hit is not None:
        action, params = local_hit
        logger.info("[router] Layer-0 short-circuit: %s -> local:%s", req.text, action)
        decision = RouteDecision(
            status="routed",
            target_type="local",
            target={"type": "local", "id": action},
            params=params,
            raw=None,
        )
        decision.candidates = candidates
        return [decision]

    # Route-decision cache (report §四十): the decision is a pure function of
    # the self-contained text and the route-index version. Keyed AFTER the
    # anaphora rewrite so session-dependent utterances never become cache keys.
    from app.core.routing import route_cache

    cache_key = await route_cache.key_for(req.text) if route_cache.enabled() else None
    cached = route_cache.get(cache_key)
    if cached is not None:
        logger.info("[router] route cache hit: %s (stats=%s)", req.text, route_cache.stats())
        from app.core.routing import native_bias

        return await native_bias.bias_decisions(cached, candidates, req.text)

    intents = await decompose.decompose(req.text)
    if not intents:
        decisions = [await route(req, candidates)]
        route_cache.put(cache_key, decisions)
        from app.core.routing import native_bias

        return await native_bias.bias_decisions(decisions, candidates, req.text)

    decisions: list[RouteDecision] = []
    contexts: list[tuple[list[RouteCandidate], str]] = []
    for intent in intents:
        sub_candidates = await retriever.retrieve(intent.text, top_k=_top_k())
        sub_req = RouteRequest(
            text=intent.text, thread_id=req.thread_id, message_id=req.message_id
        )
        decision = await route(sub_req, sub_candidates)
        params = dict(decision.params or {})
        params["_intent_text"] = intent.text
        if intent.depends_on or intent.param_exprs:
            params["_depends_on"] = intent.depends_on
            params["_param_exprs"] = intent.param_exprs
        decision.params = params
        decisions.append(decision)
        contexts.append((sub_candidates, intent.text))
    route_cache.put(cache_key, decisions)

    # Bias AFTER caching: frontmost-app context must never be baked into a
    # cached decision (native_bias module docstring).
    from app.core.routing import native_bias

    active: str | None = None
    probed = False
    out: list[RouteDecision] = []
    for decision, (sub_candidates, intent_text) in zip(decisions, contexts, strict=False):
        if decision.status == "routed" and decision.target_type == "macro":
            if not probed:
                active = await native_bias.frontmost_app_name()
                probed = True
            decision = native_bias.apply_native_app_bias(
                decision, sub_candidates, intent_text, active
            )
        out.append(decision)
    return out
