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

from app.core.environment.capabilities.registry import ActionRegistry
from app.core.routing.local_matcher import sorted_templates
from app.core.routing.schemas import VoiceInitSpec

logger = logging.getLogger(__name__)

# Voice-local actions not covered by ActionRegistry (media / self / local system).
_VOICE_LOCAL_ACTIONS: list[dict[str, Any]] = [
    {"id": "paste", "params": {}},
    {"id": "speak", "params": {}},
    {"id": "clarify", "params": {}},
    {"id": "play_pause", "params": {}},
    {"id": "next_track", "params": {}},
    {"id": "prev_track", "params": {}},
    {"id": "set_volume", "params": {"delta": "str"}},
    {"id": "mute", "params": {}},
    {"id": "unmute", "params": {}},
    {"id": "focus_app", "params": {"app": "str"}},
    {"id": "quit_app", "params": {"app": "str"}, "destructive": True},
    {"id": "press_key", "params": {"key": "str"}},
    {"id": "screenshot", "params": {}},
    {"id": "lock_screen", "params": {}, "destructive": True},
    {"id": "rename", "params": {"name": "str"}},
    {"id": "end", "params": {}},
]

# Static deterministic templates (the 50 from design §6.2.2), shipped as data.
_TEMPLATES: list[dict[str, Any]] = [
    # media
    {
        "action": "play_pause",
        "patterns": ["暂停", "停一下", "别放了", "先停"],
        "slots": {},
        "args": {"state": "pause"},
    },
    {
        "action": "play_pause",
        "patterns": ["继续", "继续播放", "接着放"],
        "slots": {},
        "args": {"state": "resume"},
    },
    {
        "action": "next_track",
        "patterns": ["下一首", "下一曲", "切歌", "换一首"],
        "slots": {},
    },
    {"action": "prev_track", "patterns": ["上一首", "上一曲", "回上一首"], "slots": {}},
    {
        "action": "set_volume",
        "patterns": [
            "音量{delta}",
            "声音{delta}",
            "把音量调{delta}",
            "把声音调{delta}",
        ],
        "slots": {"delta": "str"},
    },
    {"action": "mute", "patterns": ["静音", "别出声"], "slots": {}},
    {"action": "unmute", "patterns": ["取消静音", "恢复声音"], "slots": {}},
    # app
    {
        "action": "open_app",
        "patterns": ["打开{app}", "启动{app}", "开一下{app}"],
        "slots": {"app": "str"},
    },
    {
        "action": "focus_app",
        "patterns": ["切换到{app}", "切到{app}", "回到{app}"],
        "slots": {"app": "str"},
    },
    {
        "action": "quit_app",
        "patterns": ["退出{app}", "关闭{app}", "关掉{app}"],
        "slots": {"app": "str"},
    },
    # system
    {
        "action": "press_key",
        "patterns": ["按一下{key}", "按{key}", "按下{key}"],
        "slots": {"key": "str"},
    },
    {"action": "screenshot", "patterns": ["截图", "截屏", "屏幕截图", "截个图"], "slots": {}},
    {"action": "lock_screen", "patterns": ["锁屏", "锁定屏幕", "锁电脑"], "slots": {}},
    # self
    {"action": "clarify", "patterns": ["再说一遍", "没听清", "重说"], "slots": {}},
    {
        "action": "rename",
        "patterns": ["你以后叫{name}", "改名{name}", "你的名字是{name}"],
        "slots": {"name": "str"},
    },
    {"action": "end", "patterns": ["再见", "拜拜", "结束", "退出对话"], "slots": {}},
]

_KEY_DICT: dict[str, str] = {
    "回车": "Return",
    "空格": "Space",
    "Esc": "Escape",
    "Tab": "Tab",
    "删除": "Delete",
    "上": "Up",
    "下": "Down",
    "左": "Left",
    "右": "Right",
    "Command+C": "cmd+c",
    "Command+V": "cmd+v",
    "Command+T": "cmd+t",
    "Command+N": "cmd+n",
    "Command+W": "cmd+w",
    "Command+Q": "cmd+q",
}

_DELTA_DICT: dict[str, str] = {
    "大一点": "+10",
    "大点": "+10",
    "响一点": "+10",
    "调高": "+10",
    "小一点": "-10",
    "小点": "-10",
    "调低": "-10",
    "最大": "100",
    "一半": "50",
    "最小": "0",
    "静音": "0",
}

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
    actions: list[dict[str, Any]] = []
    try:
        for a in ActionRegistry.list_actions("desktop"):
            if a.id in ("open_app",):
                actions.append({"id": a.id, "params": a.params or {}})
    except (ValueError, OSError, RuntimeError, TypeError, KeyError) as exc:
        logger.debug("[init_spec] ActionRegistry probe failed: %s", exc)
    return actions


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


def build_init_spec() -> VoiceInitSpec:
    """Synchronous build (called by the Huey task / on-demand)."""
    apps, rank = _probe_apps()
    actions = list(_VOICE_LOCAL_ACTIONS) + _registry_actions()

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
        "key": dict(_KEY_DICT),
        "delta": dict(_DELTA_DICT),
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
