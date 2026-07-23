"""Populate `route_index` from local actions, learned skills, and the agent entry.

Full rebuild on startup + periodic refresh; an incremental `upsert_skill` is
provided for the skill-mutated hook (wired in a follow-up). All data sources are
probed defensively so a missing embedder or DB degrades to an empty index (the
router then delegates everything) rather than crashing.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any

from app.core.routing._errors import ROUTE_EXCEPTIONS
from app.core.routing.init_spec import _VOICE_LOCAL_ACTIONS
from app.core.routing.retriever import _get_embedder, get_index

logger = logging.getLogger(__name__)


def _params_to_schema(params: Any) -> dict[str, Any]:
    """Project stored skill parameters into the {name: type} schema the router
    prompt expects. Falls back to {"raw": ...} for unparseable legacy blobs."""
    if isinstance(params, dict):
        return params
    if isinstance(params, list):
        # Macro parameters are JSON-column lists of {name, type, required,
        # description}. Without this branch they collapsed to {} and the
        # route LLM HALLUCINATED param names ('inventory' for new_value) —
        # every single-intent write died at missing_required_params.
        schema: dict[str, Any] = {}
        for p in params:
            if isinstance(p, dict) and p.get("name"):
                entry: dict[str, Any] = {"type": str(p.get("type") or "string")}
                if p.get("required"):
                    entry["required"] = True
                if p.get("description"):
                    entry["description"] = str(p["description"])
                schema[str(p["name"])] = entry
        return schema
    if isinstance(params, str):
        try:
            parsed = json.loads(params)
        except (ValueError, TypeError):
            return {"raw": params}
        if isinstance(parsed, list):
            return _params_to_schema(parsed)
        if isinstance(parsed, dict):
            return parsed
        return {"raw": params}
    return {}


_LOCAL_DESC: dict[str, str] = {
    "paste": "粘贴文本到当前焦点",
    "speak": "语音播报",
    "clarify": "请求用户再说一遍",
    "rename": "给语音助理改名",
    "end": "结束对话",
    "ack": "确认",
    "cancel": "取消",
}


def _local_entries() -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    for a in _VOICE_LOCAL_ACTIONS:
        aid = a["id"]
        if aid in seen:
            continue
        seen.add(aid)
        out.append(
            {
                "id": f"local:{aid}",
                "type": "local",
                "name": aid,
                "description": _LOCAL_DESC.get(aid, aid),
                "params_schema": a.get("params") or {},
                "execution_mode": "deterministic",
                "target": aid,
            }
        )
    return out


def _agent_entry() -> dict[str, Any]:
    return {
        "id": "agent:default",
        "type": "agent",
        "name": "Agent 兜底",
        "description": "复杂多步、未覆盖任务交给 Evoloop Agent 处理",
        "params_schema": {"task": "str"},
        "execution_mode": "agentic",
        "target": "default",
    }


def _skill_entries() -> list[dict[str, Any]]:
    """Best-effort load of active learned skills; empty on any failure."""
    entries: list[dict[str, Any]] = []
    try:
        from sqlmodel import select

        from app.core.learning.skill_visibility import is_routable
        from app.infrastructure.database.sql.database import sync_session_scope
        from app.models.learning import LearnedSkill

        with sync_session_scope() as session:
            rows = session.execute(select(LearnedSkill)).scalars().all()
            for s in rows:
                if not is_routable(s):
                    continue
                sid = getattr(s, "id", None)
                name = getattr(s, "name", "") or ""
                desc = getattr(s, "description", "") or name
                mode = "deterministic" if getattr(s, "macro_id", None) else "agentic"
                entries.append(
                    {
                        "id": f"skill:{sid}",
                        "type": "skill",
                        "name": name,
                        "description": desc,
                        "params_schema": _params_to_schema(
                            getattr(s, "parameters", None)
                        ),
                        "execution_mode": mode,
                        "target": str(sid),
                    }
                )
    except (ValueError, OSError, RuntimeError, TypeError, KeyError) as exc:
        logger.debug("[route-sync] skill load skipped: %s", exc)
    return entries


def _macro_entries() -> list[dict[str, Any]]:
    """Best-effort load of verified macros; empty on any failure."""
    entries: list[dict[str, Any]] = []
    try:
        from sqlmodel import select

        from app.infrastructure.database.sql.database import sync_session_scope
        from app.models.macro import Macro

        with sync_session_scope() as session:
            stmt = select(Macro).where(
                Macro.is_active.is_(True),
                Macro.status == "verified",
            )
            rows = session.execute(stmt).scalars().all()
            for m in rows:
                mid = getattr(m, "id", None)
                name = getattr(m, "name", "") or ""
                desc = getattr(m, "description", "") or name
                entries.append(
                    {
                        "id": f"macro:{mid}",
                        "type": "macro",
                        "name": name,
                        "description": desc,
                        "triggers": _trigger_text(m),
                        "params_schema": _params_to_schema(
                            getattr(m, "parameters", None)
                        ),
                        "execution_mode": "deterministic",
                        "target": str(mid),
                    }
                )
    except (ValueError, OSError, RuntimeError, TypeError, KeyError) as exc:
        logger.debug("[route-sync] macro load skipped: %s", exc)
    return entries


_CJK_RE = re.compile(r"[一-鿿]")


async def _collect_domain_nouns() -> list[str]:
    """CJK entity aliases from active AppMaps — the domain noun set for
    session_frame's anaphora compounds (这个商品/该订单...)."""
    try:
        from sqlalchemy import select

        from app.infrastructure.database import session_scope
        from app.models.app_map import AppMap

        nouns: list[str] = []
        async with session_scope() as db:
            rows = (
                await db.execute(select(AppMap.aliases).where(AppMap.status == "active"))
            ).scalars().all()
        for aliases in rows:
            for a in aliases or []:
                if isinstance(a, str) and _CJK_RE.search(a):
                    nouns.append(a)
        return nouns
    except (OSError, RuntimeError, ValueError, TypeError, KeyError) as exc:
        logger.warning("[route-sync] domain nouns unavailable: %s", exc)
        return []


async def rebuild_route_index() -> int:
    """Full rebuild: truncate then re-embed and upsert all entries."""
    embedder = _get_embedder()
    if embedder is None:
        logger.warning(
            "[route-sync] no embedding provider; route_index left empty (router will delegate)"
        )
        return 0

    entries = _local_entries() + [_agent_entry()] + _skill_entries() + _macro_entries()
    if not entries:
        return 0

    from app.core.routing import session_frame

    session_frame.set_domain_nouns(await _collect_domain_nouns())

    texts = [_entry_embed_text(e) for e in entries]
    try:
        vectors = await embedder.embed_documents(texts)
    except ROUTE_EXCEPTIONS as exc:
        logger.warning("[route-sync] embed_documents failed: %s", exc)
        return 0

    if len(vectors) != len(entries):
        logger.warning(
            "[route-sync] embedding count mismatch (%d vs %d)",
            len(vectors),
            len(entries),
        )
        return 0

    index = get_index()
    index.truncate()
    written = index.upsert(entries, vectors)
    index.ensure_ann_index()
    logger.info("[route-sync] route_index rebuilt: %d entries", written)
    return written


def _trigger_text(s: Any) -> str:
    """Flatten a skill\'s trigger_patterns into embeddable text."""
    import json
    raw = getattr(s, "trigger_patterns", None) or []
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except ValueError:
            raw = []
    if not isinstance(raw, list):
        return ""
    return " ".join(str(t) for t in raw)


_PLACEHOLDER_RE = re.compile(r"\{\{?\s*[a-zA-Z0-9_\-]+\s*\}?\}")


def _entry_embed_text(e: dict[str, Any]) -> str:
    text = f"{e.get('name', '')} {e.get('description', '')} {e.get('triggers', '')}"
    return _PLACEHOLDER_RE.sub(" ", text).strip()
