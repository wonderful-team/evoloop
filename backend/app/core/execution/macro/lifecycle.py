"""Macro lifecycle service: persist / confirm / bulk-replace / load / delete.

All state transitions go through publish_macro_mutated so the routing index is
rebuilt by the debounced worker subscriber (single-writer contract).
"""

from __future__ import annotations

import logging
from collections.abc import Iterable

from sqlalchemy import Text, func, literal, or_, select

from app.core.events.publishers import publish_macro_mutated
from app.infrastructure.database import session_scope
from app.models.macro import Macro

logger = logging.getLogger(__name__)


def _macro_to_yaml(candidate) -> str:
    from app.core.execution.macro.schemas import MacroScript

    return MacroScript(steps=candidate.macro_script).to_yaml()


async def persist_candidates(
    *,
    app_map_id: int,
    entity: str,
    project_id: int,
    candidates: Iterable,
    member_id: int = 0,
) -> list[int]:
    """Batch-insert template-factory candidates as pending_review macros."""
    ids: list[int] = []
    async with session_scope() as db:
        for c in candidates:
            macro = Macro(
                app_map_id=app_map_id,
                entity=entity,
                name=c.name,
                description=c.description,
                trigger_patterns=c.trigger_patterns,
                parameters=c.parameters,
                macro_script=_macro_to_yaml(c),
                risk_tier=c.risk_tier,
                requires_confirmation=c.requires_confirmation,
                status="pending_review",
                is_active=False,
                app_map_version=c.app_map_version,
                project_id=project_id,
                member_id=member_id,
            )
            db.add(macro)
            await db.flush()
            ids.append(macro.id)

    for macro_id in ids:
        await publish_macro_mutated(macro_id, action="create")
    logger.info("[Macro] persisted %d candidates for app_map=%s", len(ids), app_map_id)
    return ids


async def deduplicate_macro_name(db, name: str) -> str:
    """Counter-suffix dedup for macro names within the global scope."""
    unique = name
    counter = 1
    while True:
        stmt = select(Macro.id).where(Macro.name == unique)
        if (await db.execute(stmt)).scalar_one_or_none() is None:
            return unique
        unique = f"{name}_{counter}"
        counter += 1


async def create_macro_from_synthesis(
    db,
    *,
    name: str,
    description: str = "",
    trigger_patterns: list[str] | None = None,
    parameters: list[dict] | None = None,
    macro_script: str,
    namespace: str | None = None,
    risk_tier: str = "ui",
    requires_confirmation: bool = False,
    fallback_skill_id: int | None = None,
    source_thread_id: str | None = None,
    project_id: int | None = None,
    member_id: int = 0,
) -> Macro:
    """Persist a flywheel-created macro (pending_review, is_active=False).

    Flywheel macros pair with a learned skill via ``fallback_skill_id`` (the
    心法 SOP used for self-healing) and always have ``app_map_id=None`` so
    re-surveys never obsolete them. The caller must publish_macro_mutated
    after commit.
    """
    unique_name = await deduplicate_macro_name(db, name)
    if unique_name != name:
        logger.info("Macro name collision resolved: %s -> %s", name, unique_name)

    macro = Macro(
        app_map_id=None,
        entity=None,
        name=unique_name,
        description=description,
        trigger_patterns=trigger_patterns or [],
        parameters=parameters or [],
        macro_script=macro_script,
        namespace=namespace,
        risk_tier=risk_tier,
        requires_confirmation=requires_confirmation,
        status="pending_review",
        is_active=False,
        fallback_skill_id=fallback_skill_id,
        source_thread_id=source_thread_id,
        project_id=project_id,
        member_id=member_id,
    )
    db.add(macro)
    await db.flush()
    return macro


async def load_macro(macro_id: int) -> Macro | None:
    async with session_scope() as db:
        stmt = select(Macro).where(Macro.id == macro_id)
        result = await db.execute(stmt)
        return result.scalars().first()


async def load_verified_macro(macro_id: int) -> Macro | None:
    macro = await load_macro(macro_id)
    if macro is None or not macro.is_routable():
        return None
    return macro


async def find_macro_by_name(name: str, project_id: int | None = None) -> Macro | None:
    async with session_scope() as db:
        stmt = select(Macro).where(Macro.name == name)
        if project_id is not None:
            stmt = stmt.where(Macro.project_id == project_id)
        result = await db.execute(stmt)
        return result.scalars().first()


async def list_macros(
    *,
    project_id: int | None = None,
    app_map_id: int | None = None,
    status: str | None = None,
    namespace: str | None = None,
    entity: str | None = None,
    query: str | None = None,
    limit: int | None = None,
    offset: int | None = None,
) -> list[Macro]:
    async with session_scope() as db:
        stmt = select(Macro)
        if project_id is not None:
            if project_id == 0:
                stmt = stmt.where(
                    or_(Macro.project_id == 0, Macro.project_id.is_(None))
                )
            else:
                stmt = stmt.where(Macro.project_id == project_id)
        if app_map_id is not None:
            stmt = stmt.where(Macro.app_map_id == app_map_id)
        if status is not None:
            stmt = stmt.where(Macro.status == status)
        if namespace is not None:
            stmt = stmt.where(Macro.namespace == namespace)
        if entity is not None:
            stmt = stmt.where(Macro.entity == entity)
        if query:
            keywords = [k for k in query.split() if k]
            if keywords:
                keyword_conditions = []
                for kw in keywords:
                    q = f"%{kw}%"
                    keyword_conditions.append(
                        or_(
                            Macro.name.ilike(q),
                            Macro.description.ilike(q),
                            func.coalesce(Macro.trigger_patterns, literal("[]")).cast(Text).ilike(q),
                        )
                    )
                stmt = stmt.where(or_(*keyword_conditions))
        if query and len(keywords) > 1:
            # Multi-keyword search: rank results by the number of matched keywords
            # and apply limit/offset in Python so the most relevant macros appear first.
            result = await db.execute(stmt.limit(1000))
            macros = list(result.scalars().all())

            def _score(macro):
                name = (macro.name or "").lower()
                description = (macro.description or "").lower()
                triggers = " ".join(macro.trigger_patterns or []).lower()
                score = 0
                for i, kw in enumerate(keywords):
                    kw_lower = kw.lower()
                    is_first = i == 0
                    if kw_lower in name:
                        score += 6 if is_first else 4
                    elif kw_lower in description:
                        score += 3 if is_first else 2
                    elif kw_lower in triggers:
                        score += 2 if is_first else 1
                return score

            macros.sort(key=lambda m: (-_score(m), m.id))
            start = offset or 0
            end = (start + limit) if limit is not None else None
            return macros[start:end]
        else:
            if limit is not None:
                stmt = stmt.limit(limit)
            if offset is not None:
                stmt = stmt.offset(offset)
            result = await db.execute(stmt)
            return list(result.scalars().all())


async def list_active_macro_index(project_id: int | None = None) -> list[dict]:
    """Lightweight index of routable macros for Agent context injection."""
    macros = await list_macros(project_id=project_id, status="verified")
    return [
        {
            "id": m.id,
            "name": m.name,
            "description": m.description or "",
            "entity": m.entity or "",
            "risk_tier": m.risk_tier,
        }
        for m in macros
        if m.is_active
    ]


async def confirm_macro(macro_id: int) -> bool:
    async with session_scope() as db:
        macro = await db.get(Macro, macro_id)
        if macro is None:
            return False
        macro.status = "verified"
        macro.is_active = True
        db.add(macro)
    await publish_macro_mutated(macro_id, action="update")
    return True


async def confirm_bulk(macro_ids: list[int]) -> int:
    count = 0
    async with session_scope() as db:
        for macro_id in macro_ids:
            macro = await db.get(Macro, macro_id)
            if macro is None or macro.status != "pending_review":
                continue
            macro.status = "verified"
            macro.is_active = True
            db.add(macro)
            count += 1
    for macro_id in macro_ids:
        await publish_macro_mutated(macro_id, action="update")
    return count


async def update_macro(macro_id: int, fields: dict) -> bool:
    allowed = {
        "name",
        "description",
        "trigger_patterns",
        "parameters",
        "macro_script",
        "namespace",
        "risk_tier",
        "requires_confirmation",
        "allow_self_healing",
    }
    async with session_scope() as db:
        macro = await db.get(Macro, macro_id)
        if macro is None:
            return False
        for key, value in fields.items():
            if key in allowed:
                setattr(macro, key, value)
        db.add(macro)
    await publish_macro_mutated(macro_id, action="update")
    return True


async def delete_macro(macro_id: int) -> bool:
    async with session_scope() as db:
        macro = await db.get(Macro, macro_id)
        if macro is None:
            return False
        await db.delete(macro)
    await publish_macro_mutated(macro_id, action="delete")
    return True


async def mark_obsolete_by_app_map(app_map_id: int) -> int:
    """Bulk-obsolete all macros derived from a superseded AppMap."""
    async with session_scope() as db:
        stmt = select(Macro).where(
            Macro.app_map_id == app_map_id,
            Macro.status != "obsolete",
        )
        result = await db.execute(stmt)
        rows = list(result.scalars().all())
        for macro in rows:
            macro.status = "obsolete"
            macro.is_active = False
            db.add(macro)
        ids = [m.id for m in rows]
    for macro_id in ids:
        await publish_macro_mutated(macro_id, action="obsolete")
    if ids:
        logger.info("[Macro] obsoleted %d macros for app_map=%s", len(ids), app_map_id)
    return len(ids)
