"""Skill lifecycle service — the single entry point for persisting skills.

All synthesis-style creation paths (REST synthesize, from-yaml, multimodal
recording, learn_from_trace tool) persist through ``create_from_synthesis``
so that name-collision dedup, parameter normalization, the
``(status, is_active)`` lifecycle pair, and derived parameters exist exactly
once.

The service deliberately does NOT publish the skill-mutated event: event
subscribers query the database and would not see an uncommitted row. Every
caller must ``publish_skill_mutated(action="create")`` after the surrounding
session_scope commits.

The filesystem importer (SkillImporter) is the one intentional exception:
user-authored SKILL.md files are validated on import and may enter as
verified/candidate directly.

This module also owns the idempotent startup data repairs for the learning
schema (legacy status pairs, double-encoded trace state snapshots, and the
one-time drop of the removed smart-synthesis table), wired from
``app.initial_data``.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.learning import LearnedSkill

logger = logging.getLogger(__name__)

# {{ name }} / {{ a.b }} placeholders consumed by MacroEngine injection.
_PLACEHOLDER_RE = re.compile(r"\{\{\s*([A-Za-z_]\w*)\s*(?:\.[^}]+)?\}\}")


def derive_parameters_from_macro(macro_script: str | None) -> list[dict[str, Any]]:
    """Derive required string parameters from ``{{ name }}`` placeholders.

    A placeholder left unsubstituted would silently corrupt replay, so every
    derived parameter is required. Returns [] when there is nothing to derive.
    """
    if not macro_script:
        return []
    names = sorted({m.group(1) for m in _PLACEHOLDER_RE.finditer(macro_script)})
    return [{"name": n, "type": "string", "required": True} for n in names]


def normalize_parameters(parameters: Any) -> list[dict[str, Any]]:
    """Coerce SkillParameter objects / dicts / JSON strings into plain dicts."""
    if parameters is None:
        return []
    if isinstance(parameters, str):
        try:
            parameters = json.loads(parameters)
        except (ValueError, TypeError):
            return []
    if not isinstance(parameters, list):
        return []
    out: list[dict[str, Any]] = []
    for p in parameters:
        if hasattr(p, "model_dump"):
            p = p.model_dump()
        elif not isinstance(p, dict) and hasattr(p, "__dict__"):
            p = {k: v for k, v in vars(p).items() if not k.startswith("_")}
        if isinstance(p, dict) and p.get("name"):
            out.append(
                {
                    "name": str(p["name"]),
                    "type": str(p.get("type") or "string"),
                    "description": str(p.get("description") or ""),
                    "required": bool(p.get("required", True)),
                    "default": p.get("default"),
                }
            )
    return out


def missing_required_params(parameters: Any, provided: dict[str, Any] | None) -> list[str]:
    """Names of required skill parameters absent from the execution request.

    Shared by the REST execute endpoint and the voice executor so a macro
    never runs with unsubstituted ``{{ name }}`` placeholders.
    """
    provided = provided or {}
    try:
        params = json.loads(parameters) if isinstance(parameters, str) else parameters
    except (ValueError, TypeError):
        return []
    if not isinstance(params, list):
        return []
    missing = []
    for p in params:
        if isinstance(p, dict) and p.get("required"):
            name = p.get("name")
            if name and provided.get(name) in (None, ""):
                missing.append(str(name))
    return missing


async def deduplicate_name(db: AsyncSession, name: str, member_id: int) -> str:
    """Counter-suffix dedup within the member's visible scope (0 + own)."""
    unique = name
    counter = 1
    while True:
        stmt = (
            select(LearnedSkill.id)
            .where(
                or_(LearnedSkill.member_id == 0, LearnedSkill.member_id == member_id)
            )
            .where(LearnedSkill.name == unique)
        )
        if (await db.execute(stmt)).scalar_one_or_none() is None:
            return unique
        unique = f"{name}_{counter}"
        counter += 1


async def create_from_synthesis(
    db: AsyncSession,
    *,
    name: str,
    member_id: int = 0,
    description: str = "",
    trigger_patterns: list[str] | None = None,
    parameters: Any = None,
    derive_parameters: bool = False,
    instructions: str | None = None,
    execution_mode: str | None = None,
    macro_script: str | None = None,
    namespace: str | None = None,
    preconditions: Any = None,
    tools_used: list[str] | None = None,
    source_thread_id: str | None = None,
    source_session_id: str | None = None,
    skill_source: str | None = None,
    validation_report: dict | None = None,
) -> LearnedSkill:
    """Persist a newly synthesized skill as (pending_review, is_active=False).

    Handles name-collision dedup and parameter normalization. When
    ``derive_parameters`` is set and no explicit parameters are given, they
    are derived from ``{{ name }}`` placeholders in the macro script. The
    caller must publish the create event after commit (see module docstring).
    """
    unique_name = await deduplicate_name(db, name, member_id)
    if unique_name != name:
        logger.info("Skill name collision resolved: %s -> %s", name, unique_name)

    param_list = normalize_parameters(parameters)
    if not param_list and derive_parameters:
        param_list = derive_parameters_from_macro(macro_script)

    skill = LearnedSkill(
        member_id=member_id,
        name=unique_name,
        description=description,
        namespace=namespace,
        trigger_patterns=trigger_patterns or [],
        parameters=param_list,
        preconditions=preconditions,
        instructions=instructions,
        tools_used=tools_used,
        source_thread_id=source_thread_id,
        source_session_id=source_session_id,
        execution_mode=execution_mode,
        macro_script=macro_script,
        skill_source=skill_source,
        validation_report=validation_report,
        status="pending_review",
        is_active=False,
    )
    db.add(skill)
    await db.flush()
    return skill


def repair_state_snapshot_encoding() -> int:
    """Repair double-encoded ``TraceEvent.state_snapshot`` rows (sync, startup-safe).

    Recorder endpoints historically stored ``json.dumps`` strings into the
    JSON column, so those rows came back as ``str`` and were silently dropped
    by the trace parser (pydantic rejects ``str`` for ``state_context``).
    Writers now store dicts; this repairs rows written before the fix.
    Idempotent; unparseable rows are skipped at debug level.

    Returns the number of rows repaired.
    """
    from app.infrastructure.database.sql.database import sync_session_scope
    from app.models.learning import TraceEvent

    repaired = 0
    with sync_session_scope() as session:
        rows = (
            session.execute(
                select(TraceEvent).where(TraceEvent.state_snapshot.is_not(None))
            )
            .scalars()
            .all()
        )
        for row in rows:
            if not isinstance(row.state_snapshot, str):
                continue
            try:
                decoded = json.loads(row.state_snapshot)
            except (ValueError, TypeError):
                logger.debug(
                    "Skipping unparseable state_snapshot on TraceEvent %s", row.id
                )
                continue
            if not isinstance(decoded, dict):
                continue
            row.state_snapshot = decoded
            repaired += 1

    if repaired:
        logger.info("Repaired %d double-encoded state_snapshot row(s)", repaired)
    return repaired


def drop_legacy_learning_tables() -> list[str]:
    """Drop removed learning tables if they still exist (idempotent).

    Chain D (smart-synthesis) and the few-shot RouterTrainingData model were
    deleted; their models are gone so create_all no longer manages the
    tables. Existing databases may still carry the orphans — drop them once
    at startup. Runs as a no-op forever after.

    Returns the list of table names dropped on this run.
    """
    from sqlalchemy import inspect, text

    from app.infrastructure.database.sql.database import db_resource_manager

    engine = db_resource_manager.sync_engine
    if engine is None:
        return []

    legacy_tables = ("synthesis_jobs", "router_training_data")
    existing = set(inspect(engine).get_table_names())
    to_drop = [t for t in legacy_tables if t in existing]
    if not to_drop:
        return []

    with engine.begin() as conn:
        for table in to_drop:
            conn.execute(text(f"DROP TABLE {table}"))
    logger.info("Dropped legacy orphan tables: %s", ", ".join(to_drop))
    return to_drop


def migrate_legacy_status_rows() -> dict[str, int]:
    """Idempotent repair of pre-convergence skill rows (startup-safe, sync).

    - ``draft`` -> ``pending_review`` + ``is_active=False``: legacy
      ``learn_from_trace`` rows were silently unroutable (status gate) AND
      could not be confirmed (confirm only accepts pending_review). They now
      surface in the UI for a one-time re-confirmation.
    - status ``active`` -> ``verified``: the routable set tightened to
      {verified}; "active" was never written by any code path, so this only
      repairs hand-edited rows and preserves their routability.

    Runs at every startup (wired from app.initial_data); returns affected
    row counts for logging. Safe to run repeatedly.
    """
    from sqlalchemy import update

    from app.infrastructure.database.sql.database import sync_session_scope

    with sync_session_scope() as session:
        draft_res = session.execute(
            update(LearnedSkill)
            .where(LearnedSkill.status == "draft")
            .values(status="pending_review", is_active=False)
        )
        active_res = session.execute(
            update(LearnedSkill)
            .where(LearnedSkill.status == "active")
            .values(status="verified")
        )

    counts = {
        "draft_to_pending_review": draft_res.rowcount or 0,
        "active_to_verified": active_res.rowcount or 0,
    }
    if any(counts.values()):
        logger.info("Skill lifecycle migration applied: %s", counts)
    return counts
