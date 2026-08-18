"""Build the RouteCatalog (Layer-0 dynamic data) from backend sources.

Data sources (see design §6.4): Environment (host apps / usage rank), Atlas
(bundle ids), plus voice-local media / self / system actions that the registry
does not cover. Everything is produced as data; the client does deterministic
matching only. All sources are probed defensively so the spec still builds on
first run or non-macOS hosts.

Language-specific aliases, templates, and voice-local actions are loaded
from ``app.core.routing.routing_data`` (``app/core/routing/data/{lang}/``).  The
spec is further enriched with Atlas aliases and DB macro triggers; it is then
returned by ``/route/init`` for client-side deterministic matching and is also
used by the BERT macro resolution path.
"""

from __future__ import annotations

import asyncio
import logging
import re
from datetime import datetime, timezone
from typing import Any

from app.core.routing.pinyin import to_pinyin
from app.core.routing.routing_data import get_store
from app.core.routing.schemas import RouteCatalog

logger = logging.getLogger(__name__)

_routing_store = get_store()


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
    except Exception:
        logger.debug("[init_spec] list_installed_apps failed", exc_info=True)
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
        py = to_pinyin(name)
        if py:
            entry["pinyin"] = py
        entries.append(entry)
        rank.append(name)
    return entries, rank


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


async def enrich_spec_with_atlas_aliases(spec: RouteCatalog) -> RouteCatalog:
    """Fold Atlas-surveyed Chinese aliases into the L0 app slot dictionary.

    The L0 client matches '打开微信' via slot_dictionaries['app'][].aliases;
    those aliases exist only in Atlas survey data and were never shipped —
    the client could not resolve 微信/飞书 until now (M5).
    """
    try:
        triples = await _atlas_app_aliases()
    except Exception:
        logger.debug("[init_spec] atlas alias probe failed", exc_info=True)
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


async def enrich_spec_with_macro_triggers(spec: RouteCatalog) -> RouteCatalog:
    """从 DB 加载 routable Macro 的 trigger_patterns，注入为 L0 templates。

    作用域：**全部已确认宏**（全局 + 所有项目）。L0 spec 是全局共享的
    路由表（客户端 GET /route/init 拉取，worker 后台构建），不应依赖运行时
    的"当前活跃项目"——否则 worker 构建（project_id=0）会漏掉项目级宏
    （如 mall-backend 的 #958 登录后台），导致语音"登录后台"无法在 L0
    命中而错误下沉到 Agent。

    冲突去重：preset 优先于用户；同级别下最新确认的宏优先（created_at desc），
    与 ``MacroResolver`` 的运行时选择保持一致 —— 用户新确认的宏立即生效。
    """
    from app.core.execution.macro import list_macros

    try:
        macros = await list_macros(status="verified", is_active=True)
        macros.sort(
            key=lambda m: (
                m.namespace != "preset",
                -(m.created_at.timestamp() if m.created_at else 0),
            )
        )
    except Exception:
        logger.debug("[init_spec] macro trigger load skipped", exc_info=True)
        return spec

    seen_patterns: set[tuple[int | None, str]] = set()
    added = 0
    for macro in macros:
        triggers = macro.trigger_patterns or []
        deduped: list[str] = []
        for trigger in triggers:
            pattern = trigger.replace("{{", "{").replace("}}", "}")
            # Dedupe per project (global None is its own scope): a project macro
            # and a global macro may share a trigger; the matcher picks the
            # current project's first, global as fallback.
            key = (macro.project_id, pattern)
            if key in seen_patterns:
                logger.debug("[init_spec] trigger '%s' skipped (macro %d, already bound)", pattern, macro.id)
                continue
            seen_patterns.add(key)
            deduped.append(pattern)
        if not deduped:
            continue
        slot_names = [p.get("name") for p in (macro.parameters or []) if p.get("name")]
        slots = dict.fromkeys(slot_names, "str")
        spec.templates.append({
            "action": f"macro:{macro.id}",
            "patterns": deduped,
            "slots": slots,
            "args": {},
            "project_id": macro.project_id,
        })
        added += 1
    logger.info(
        "[init_spec] enriched %d macro templates (%d macros scanned, %d patterns deduped)",
        added,
        len(macros),
        len(seen_patterns),
    )
    return spec


def build_init_spec() -> RouteCatalog:
    """Synchronous build (called by the Huey task / on-demand).

    Uses the language-specific templates / aliases / voice-local actions
    exported by ``app.core.routing.routing_data``.  The returned spec should then
    be enriched with Atlas aliases and DB macro triggers before use.
    """
    apps, rank = _probe_apps()

    # Merge static app entries from the language pack into the app slot dictionary.
    # These entries ensure common apps can be routed by L0 even on hosts where
    # the macOS installed-apps probe is unavailable; the client is still
    # responsible for verifying whether the app is actually installed.
    aliases = dict(_routing_store.aliases)
    installed_names = {e.get("name") for e in apps if isinstance(e, dict)}
    for entry in list(_routing_store.apps):
        if not isinstance(entry, dict):
            continue
        name = entry.get("name")
        if name and name not in installed_names:
            if not entry.get("pinyin"):
                entry = dict(entry)
                py = to_pinyin(str(name))
                if py:
                    entry["pinyin"] = py
            apps.append(entry)
            installed_names.add(name)
            rank.append(name)
        for alias in entry.get("aliases", []) or []:
            if alias and name:
                aliases.setdefault(alias, name)

    # Defense-in-depth: inject well-known spoken aliases when the canonical app is
    # installed but the Chinese spoken name is not already an installed display name.
    # This lets "打开微信" match even if the system lists the app as "WeChat" and
    # Atlas has not surveyed it.
    if _routing_store.lang == "zh":
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

    version = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S%f")
    return RouteCatalog(
        version=version,
        actions=list(_routing_store.voice_local_actions),
        templates=_sorted_templates(_routing_store.templates),
        slot_dictionaries=slot_dictionaries,
        aliases=aliases,
        polite_prefixes=_routing_store.polite_prefixes,
        polite_suffixes=_routing_store.polite_suffixes,
        slot_filler_prefixes=_routing_store.slot_filler_prefixes,
        slot_filler_suffixes=_routing_store.slot_filler_suffixes,
        app_suffix_noise=_routing_store.app_suffix_noise,
        free_text_reject_markers=_routing_store.free_text_reject_markers,
        slot_filler_chars=_routing_store.slot_filler_chars,
        default_apps={"browser": "Safari", "music": "Apple Music"},
        app_usage_rank=rank[:50],
        capabilities=capabilities,
        preferences={"lang": _routing_store.lang},
    )


_SLOT_RE = re.compile(r"\{[a-zA-Z0-9_]+\}")


def _template_literal_len(pattern: str) -> int:
    return len(_SLOT_RE.sub("", pattern))


def _sorted_templates(templates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Rule 2 shipping order: longest-literal patterns first."""
    return sorted(
        templates,
        key=lambda t: max(
            (_template_literal_len(p) for p in t.get("patterns", [])), default=0
        ),
        reverse=True,
    )


async def build_and_enrich_spec() -> RouteCatalog:
    """Full async build: base spec + Atlas aliases + DB macro triggers."""
    spec = await asyncio.to_thread(build_init_spec)
    spec = await enrich_spec_with_atlas_aliases(spec)
    spec = await enrich_spec_with_macro_triggers(spec)
    return spec
