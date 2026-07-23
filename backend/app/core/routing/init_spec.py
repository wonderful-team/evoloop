"""Build the VoiceInitSpec (Layer-0 dynamic data) from backend sources.

Data sources (see design §6.4): Environment (host apps / usage rank), Atlas
(bundle ids), ActionRegistry (desktop safe subset), plus voice-local media /
self / system actions that the registry does not cover. Everything is produced
as data; the client does deterministic matching only. All sources are probed
defensively so the spec still builds on first run or non-macOS hosts.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from app.core.routing.local_matcher import sorted_templates
from app.core.routing.schemas import VoiceInitSpec

logger = logging.getLogger(__name__)

# Voice-local actions not covered by ActionRegistry (Evoloop self commands).
_VOICE_LOCAL_ACTIONS: list[dict[str, Any]] = [
    {"id": "paste", "params": {}},
    {"id": "speak", "params": {}},
    {"id": "clarify", "params": {}},
    {"id": "rename", "params": {"name": "str"}},
    {"id": "end", "params": {}},
    {"id": "ack", "params": {}},
    {"id": "cancel", "params": {}},
]

# Static deterministic templates for Evoloop self commands.
_TEMPLATES: list[dict[str, Any]] = [
    {"action": "clarify", "patterns": ["再说一遍", "没听清", "重说"], "slots": {}},
    {
        "action": "rename",
        "patterns": ["你以后叫{name}", "改名{name}", "你的名字是{name}"],
        "slots": {"name": "str"},
    },
    {"action": "end", "patterns": ["再见", "拜拜", "结束", "退出对话"], "slots": {}},
    {"action": "ack", "patterns": ["对对对", "没错", "就这个", "可以", "对的", "是的"], "slots": {}},
    {"action": "cancel", "patterns": ["算了", "不用了", "不要", "取消"], "slots": {}},
]

_ALIASES: dict[str, str] = {"音乐": "Apple Music", "浏览器": "Safari"}


def _pinyin(text: str) -> str | None:
    """Best-effort pinyin; None when pypinyin is unavailable (client degrades)."""
    try:
        from pypinyin import lazy_pinyin  # type: ignore
    except ImportError:
        return None
    try:
        return "".join(lazy_pinyin(text))
    except (ValueError, RuntimeError, TypeError):
        return None


def _probe_apps() -> tuple[list[dict[str, Any]], list[str]]:
    """Return (app_entries, usage_rank). Tolerates non-macOS / missing data."""
    entries: list[dict[str, Any]] = []
    rank: list[str] = []
    try:
        from app.infrastructure.drivers.macos import macos_driver
    except ImportError:
        return entries, rank

    raw: list[Any] = []
    try:
        raw = macos_driver.list_installed_apps() or []
    except (ValueError, OSError, RuntimeError, TypeError, KeyError) as exc:
        logger.debug("[init_spec] list_installed_apps failed: %s", exc)
        return entries, rank

    for item in raw:
        if isinstance(item, str):
            name, bundle = item, ""
        elif isinstance(item, dict):
            name = item.get("name") or item.get("app_name") or ""
            bundle = item.get("bundle_id") or ""
        else:
            continue
        if not name:
            continue
        entry: dict[str, Any] = {"name": name, "bundle_id": bundle, "aliases": []}
        py = _pinyin(name)
        if py:
            entry["pinyin"] = py
        entries.append(entry)
        rank.append(name)
    return entries, rank


def _registry_actions() -> list[dict[str, Any]]:
    """Legacy registry probe — all previously registered actions are now preset Macros."""
    return []


async def _atlas_app_aliases() -> list[tuple[str, str, str]]:
    """(canonical, bundle_id, spoken-alias) triples, derived from survey data.

    The application menu is conventionally the FIRST AXMenuBarItem (after the
    Apple root), and its label is the app's display name ('微信' for WeChat,
    '飞书' for Lark, 'Chrome' for Chrome). When it differs from the canonical
    name it IS the spoken alias — no name-reverse-engineering needed. Matching
    is by bundle_id: the installed-apps list may already use the localized
    name ('飞书') while Atlas stored 'Lark'.
    """
    from app.core.atlas.adapters.sql_store import SQLAtlasStore
    from app.core.atlas.surveyor import MENUBAR_STATE_ID

    store = SQLAtlasStore()
    out: list[tuple[str, str, str]] = []
    for info in await store.list_apps():
        detail = await store.get_state_detail(info.bundle_id, MENUBAR_STATE_ID)
        if detail is None:
            continue
        roots = [
            (el.get("label") or "").strip()
            for el in detail.elements
            if isinstance(el, dict)
            and el.get("role") == "AXMenuBarItem"
            and (el.get("label") or "").strip()
            and (el.get("label") or "").strip().lower() not in ("apple", "")
        ]
        if not roots:
            continue
        canonical, display = info.app_name, roots[0]
        if display.lower() != canonical.lower():
            out.append((canonical, info.bundle_id, display))
    return out


async def enrich_spec_with_atlas_aliases(spec: VoiceInitSpec) -> VoiceInitSpec:
    """Fold Atlas-surveyed Chinese aliases into the L0 app slot dictionary.

    The L0 client matches '打开微信' via slot_dictionaries['app'][].aliases;
    those aliases exist only in Atlas survey data and were never shipped —
    the client could not resolve 微信/飞书 until now (M5).
    """
    try:
        triples = await _atlas_app_aliases()
    except (ValueError, OSError, RuntimeError, TypeError, KeyError) as exc:
        logger.debug("[init_spec] atlas alias probe failed: %s", exc)
        return spec
    if not triples:
        return spec
    by_bundle = {b: (c, a) for c, b, a in triples}
    by_name = {c.lower(): (c, a) for c, _b, a in triples}
    app_entries = spec.slot_dictionaries.get("app") or []
    matched: set[str] = set()
    for entry in app_entries:
        hit = by_bundle.get(entry.get("bundle_id") or "") or by_name.get(
            (entry.get("name") or "").lower()
        )
        if not hit:
            continue
        canonical, alias = hit
        matched.add(canonical.lower())
        if alias == entry.get("name"):
            continue  # 安装名已是中文别名（如 飞书），无需自指
        merged = list(dict.fromkeys([*entry.get("aliases", []), alias]))
        entry["aliases"] = merged
        spec.aliases.setdefault(alias, entry["name"])

    # Installed-apps probe is actually a running-apps snapshot and may miss the
    # real app entirely ('Lark Helper' but no 'Lark'); Atlas survey data is
    # authoritative, so backfill unmatched triples as standalone entries.
    for canonical, bundle_id, alias in triples:
        if canonical.lower() in matched:
            continue
        app_entries.append(
            {"name": canonical, "bundle_id": bundle_id, "aliases": [alias]}
        )
        spec.aliases.setdefault(alias, canonical)
    return spec


async def enrich_spec_with_macro_triggers(spec: VoiceInitSpec) -> VoiceInitSpec:
    """从 DB 加载 routable Macro 的 trigger_patterns，注入为 L0 templates。

    作用域：全局（project_id IS NULL）+ 当前项目（shared_state.project_id）。
    冲突去重：preset 优先于用户，同 pattern 只保留第一条。
    """
    from app.core.shared_state import shared_state
    from app.infrastructure.database import session_scope
    from app.models.macro import Macro
    from sqlmodel import select, case

    current_project_id = int(await shared_state.get("project_id", "0"))

    try:
        async with session_scope() as session:
            stmt = select(Macro).where(
                Macro.is_active.is_(True),
                Macro.status == "verified",
                (Macro.project_id.is_(None)) | (Macro.project_id == current_project_id),
            ).order_by(
                case((Macro.namespace == "preset", 0), else_=1),
                Macro.created_at.asc(),
            )
            macros = (await session.execute(stmt)).scalars().all()
    except (ValueError, OSError, RuntimeError, TypeError, KeyError) as exc:
        logger.debug("[init_spec] macro trigger load skipped: %s", exc)
        return spec

    seen_patterns: set[str] = set()
    added = 0
    for macro in macros:
        triggers = macro.trigger_patterns or []
        deduped: list[str] = []
        for trigger in triggers:
            pattern = trigger.replace("{{", "{").replace("}}", "}")
            if pattern in seen_patterns:
                logger.warning(
                    "[init_spec] trigger '%s' skipped (macro %d, already bound)",
                    pattern, macro.id,
                )
                continue
            seen_patterns.add(pattern)
            deduped.append(pattern)
        if not deduped:
            continue
        slot_names = [p.get("name") for p in (macro.parameters or []) if p.get("name")]
        slots = {name: "str" for name in slot_names}
        spec.templates.append({
            "action": f"macro:{macro.id}",
            "patterns": deduped,
            "slots": slots,
            "args": {},
        })
        added += 1
    logger.info("[init_spec] enriched %d macro templates (%d macros scanned, %d patterns deduped)",
                added, len(macros), len(seen_patterns))
    return spec


def build_init_spec() -> VoiceInitSpec:
    """Synchronous build (called by the Huey task / on-demand)."""
    apps, rank = _probe_apps()
    actions = list(_VOICE_LOCAL_ACTIONS)

    # Inject well-known spoken aliases when the canonical app is installed but
    # the Chinese spoken name is not already an installed display name. This
    # lets "打开微信" match as a local action even if the system lists the app
    # as "WeChat" and Atlas has not surveyed the alias yet.
    installed_names = {e.get("name") for e in apps if isinstance(e, dict)}
    aliases = dict(_ALIASES)
    if "WeChat" in installed_names and "微信" not in installed_names:
        aliases.setdefault("微信", "WeChat")

    slot_dictionaries: dict[str, Any] = {
        "app": apps,
    }

    capabilities: dict[str, Any] = {
        "platforms": ["desktop"],
        "accessibility": True,  # client enforces; backend assumes granted
        "input_monitoring": True,
        "android_connected": False,
        "network": True,
        "disabled_actions": [],
    }

    version = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    return VoiceInitSpec(
        version=version,
        actions=actions,
        templates=sorted_templates(_TEMPLATES),
        slot_dictionaries=slot_dictionaries,
        aliases=aliases,
        default_apps={"browser": "Safari", "music": "Apple Music"},
        app_usage_rank=rank[:50],
        capabilities=capabilities,
        preferences={"lang": "zh"},
    )
