"""
Native macro generator (M3) — AtlasApp (macOS AX survey) -> deterministic
native macros, zero LLM at generation AND runtime.

Macro kinds (design doc v0.3 G2):
  1. Menu macros: menubar label-chain -> ax_menu_press (focus-free).
     - dynamic menu roots (bookmarks/history/windows/tabs) skipped;
     - destructive leaves skipped (delete/erase/format...);
     - quit/close-all style leaves generated with requires_confirmation=True;
     - depth capped at 3.
  2. Field macros: named text fields (AXTextField/AXSearchField/AXComboBox)
     -> ax_set_value with {{text}} param; fields advertising AXConfirm get a
     confirm step ("address bar -> navigate"). Fields inside outline/table
     containers are rejected (M1.5 file-name-cell trap).

Persistence mirrors lifecycle.persist_candidates but self-contained:
app_map_id=None (native surveys are not web app_maps), namespace=NATIVE_NS.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field

from app.core.events.publishers import publish_macro_mutated
from app.infrastructure.database import session_scope
from app.models.macro import Macro

logger = logging.getLogger(__name__)

NATIVE_NS = "native_macos"
MAX_MENU_DEPTH = 3

# Menu roots whose children are ALL dynamic content (bookmarks/history) or
# OS-level junk with badge-suffixed labels ("App Store…，9项更新").
DYNAMIC_MENU_ROOTS = {
    "apple",
    "书签",
    "bookmarks",
    "历史记录",
    "history",
    "最近使用",
    "最近使用的项目",
    "最近打开",
    "open recent",
    "recents",
    "recent items",
}

# 标签页/窗口 menus mix static commands (新标签页/最小化) with enumerated
# dynamic entries (open tabs/windows) — keep the root, filter the leaves.
_ENUMERATED_LEAF = re.compile(r"^\d+[\.、)]")
MAX_LEAF_LABEL_LEN = 30

# macOS 标准窗口平铺子菜单：每个应用内容全同 + 内部近亲对（左侧与右侧 vs
# 右侧与左侧），是跨应用路由混淆的最大来源（M4 语料实测 27 miss 中 15 条）。
# 系统级窗口管理交给系统快捷键/Agent，不出宏。
TILING_SUBMENUS = {"全屏幕拼贴", "移动与调整大小", "move & resize", "tile", "tiling"}

# Leaves never generated (destructive, irreversible).
SKIP_LEAF = re.compile(
    r"delete|删除|清空|erase|抹掉|format|格式化|uninstall|卸载|empty trash|倒空废纸篓",
    re.IGNORECASE,
)

# Leaves generated but gated behind user confirmation.
CONFIRM_LEAF = re.compile(
    r"退出|quit|close all|全部关闭|关闭所有|force quit|强制退出|注销|log ?out|sign out"
    r"|restart|重启|shutdown|关机|hide others|隐藏其他",
    re.IGNORECASE,
)

FIELD_ROLES = {"AXTextField", "AXSearchField", "AXComboBox"}
FIELD_CONTAINER_RE = re.compile(r"AXOutline|AXTable", re.IGNORECASE)
ADDRESS_FIELD_RE = re.compile(r"address|地址|搜索栏|search", re.IGNORECASE)
# Junk field labels observed in surveys (log-level text misread as a field).
FIELD_LABEL_STOPWORDS = {
    "error",
    "warn",
    "warning",
    "info",
    "debug",
    "fatal",
    "log",
    "错误",
    "警告",
    "日志",
}


@dataclass
class NativeMacroCandidate:
    name: str
    description: str
    trigger_patterns: list[str]
    parameters: list[dict]
    steps: list[dict]
    risk_tier: str = "ui"
    requires_confirmation: bool = False
    labels_chain: list[str] = field(default_factory=list)


def _open_step(bundle_id: str) -> dict:
    return {
        "step_number": 1,
        "type": "action",
        "event_type": "open_app",
        "source": "desktop",
        "description": "确保应用运行（免焦点）",
        "payload": {"bundle_id": bundle_id, "focus": False},
    }


def _menu_chains(menubar_elements: list[dict]) -> list[tuple[list[str], dict]]:
    """[(label_chain, leaf_element)] for actionable named menu items."""
    label_of = {e["ax_path"]: e["label"].strip() for e in menubar_elements if e["label"].strip()}
    out: list[tuple[list[str], dict]] = []
    for e in menubar_elements:
        if e["role"] not in ("AXMenuItem", "AXMenuBarItem") or not e["label"].strip():
            continue
        actions = (e.get("metadata") or {}).get("extra", {}).get("actions") or []
        if not actions and e["role"] != "AXMenuBarItem":
            continue
        chain: list[str] = []
        p = e["ax_path"]
        while " > " in p:
            p = p.rsplit(" > ", 1)[0]
            if label_of.get(p):
                chain.append(label_of[p])
        chain.reverse()
        chain.append(e["label"].strip())
        out.append((chain, e))
    return out


def generate_menu_macros(bundle_id: str, app_name: str, menubar_elements: list[dict]) -> list[NativeMacroCandidate]:
    candidates: list[NativeMacroCandidate] = []
    seen: set[tuple[str, ...]] = set()
    for chain, _leaf in _menu_chains(menubar_elements):
        if len(chain) < 2 or len(chain) > MAX_MENU_DEPTH:
            # chain==1 = 按根菜单（仅弹出菜单，非用户指令，且制造"Chrome Chrome"
            # 式垃圾宏与跨应用混淆对）
            continue
        root = chain[0].lower()
        if root in DYNAMIC_MENU_ROOTS:
            continue
        if any(part.lower() in TILING_SUBMENUS for part in chain[1:-1]):
            continue
        leaf_label = chain[-1]
        if SKIP_LEAF.search(leaf_label):
            continue
        if _ENUMERATED_LEAF.search(leaf_label) or len(leaf_label) > MAX_LEAF_LABEL_LEN:
            continue
        key = tuple(chain)
        if key in seen:
            continue
        seen.add(key)
        steps = [
            _open_step(bundle_id),
            {
                "step_number": 2,
                "type": "action",
                "event_type": "ax_menu_press",
                "source": "desktop",
                "description": f"菜单 {' > '.join(chain)}",
                "payload": {"bundle_id": bundle_id, "menu_labels": chain},
            },
        ]
        name = f"{app_name} {'>'.join(chain)}"
        candidates.append(
            NativeMacroCandidate(
                name=name,
                description=f"{app_name} 菜单 {' > '.join(chain)}（原生免焦点）",
                trigger_patterns=[leaf_label, f"{app_name}{leaf_label}"],
                parameters=[],
                steps=steps,
                risk_tier="ui",
                requires_confirmation=bool(CONFIRM_LEAF.search(leaf_label)),
                labels_chain=chain,
            )
        )
    return candidates


def generate_field_macros(
    bundle_id: str, app_name: str, window_elements: list[dict]
) -> list[NativeMacroCandidate]:
    candidates: list[NativeMacroCandidate] = []
    seen: set[str] = set()
    for e in window_elements:
        if e["role"] not in FIELD_ROLES:
            continue
        label = e["label"].strip()
        if not label or len(label) > 40:
            continue
        if label.lower() in FIELD_LABEL_STOPWORDS:
            continue
        ax_path = e["ax_path"]
        if FIELD_CONTAINER_RE.search(ax_path) or not ax_path.startswith("window"):
            continue
        if ax_path in seen:
            continue
        seen.add(ax_path)
        actions = (e.get("metadata") or {}).get("extra", {}).get("actions") or []
        is_address = bool(ADDRESS_FIELD_RE.search(label))
        steps = [
            _open_step(bundle_id),
            {
                "step_number": 2,
                "type": "action",
                "event_type": "ax_set_value",
                "source": "desktop",
                "description": f"向 {label} 写入文本",
                "payload": {
                    "bundle_id": bundle_id,
                    "role": e["role"],
                    "label": label,
                    "ax_path": ax_path,
                    "text": "{{text}}",
                },
            },
        ]
        if "AXConfirm" in actions:
            steps.append(
                {
                    "step_number": 3,
                    "type": "action",
                    "event_type": "ax_press",
                    "source": "desktop",
                    "description": f"确认 {label}（AXConfirm）",
                    "payload": {
                        "bundle_id": bundle_id,
                        "role": e["role"],
                        "label": label,
                        "ax_path": ax_path,
                        "ax_action": "AXConfirm",
                    },
                }
            )
        if is_address:
            triggers = ["打开{{text}}", "访问{{text}}", f"在{app_name}打开{{{{text}}}}"]
            name = f"{app_name} 打开网址"
        else:
            triggers = [
                f"在{app_name}的{label}输入{{{{text}}}}",
                f"{app_name}{label}输入{{{{text}}}}",
            ]
            name = f"{app_name} {label}输入"
        candidates.append(
            NativeMacroCandidate(
                name=name,
                description=f"{app_name} 字段 {label} 文本输入（AXSetValue 读回验证）",
                trigger_patterns=triggers,
                parameters=[
                    {
                        "name": "text",
                        "type": "string",
                        "required": True,
                        "description": f"写入{label}的文本",
                    }
                ],
                steps=steps,
                risk_tier="data" if not is_address else "ui",
            )
        )
    return candidates


def generate_for_atlas_app(bundle_id: str, app_name: str, states: dict[str, dict]) -> list[NativeMacroCandidate]:
    """states: {state_id: {"window_title": str, "elements": [element dicts]}}
    (element dicts carry role/label/ax_path/metadata.extra.actions)."""
    from app.core.atlas.surveyor import MENUBAR_STATE_ID

    candidates: list[NativeMacroCandidate] = []
    menubar = states.get(MENUBAR_STATE_ID)
    if menubar:
        candidates.extend(generate_menu_macros(bundle_id, app_name, menubar["elements"]))
    for sid, state in states.items():
        if sid == MENUBAR_STATE_ID:
            continue
        candidates.extend(generate_field_macros(bundle_id, app_name, state["elements"]))
    return candidates


async def persist_native_macros(
    candidates: list[NativeMacroCandidate],
    project_id: int | None = None,
    member_id: int = 0,
) -> list[int]:
    """Insert as pending_review macros (namespace=native_macos) + publish.

    Idempotent: pre-existing native_macos rows with the same names are
    deleted first (regeneration replaces, never duplicates)."""
    from sqlalchemy import delete

    from app.core.execution.macro.schemas import MacroScript

    # 每批按应用前缀替换（persist 逐应用调用，绝不能整 namespace 清空——
    # 否则后一批会抹掉前一批；规则演进剔除的旧名也不会残留）
    prefixes = {c.name.split(" ", 1)[0] for c in candidates}
    ids: list[int] = []
    async with session_scope() as db:
        for prefix in prefixes:
            stmt = delete(Macro).where(Macro.namespace == NATIVE_NS, Macro.name.startswith(f"{prefix} "))
            await db.execute(stmt)
        for c in candidates:
            script = MacroScript(steps=c.steps).to_yaml()
            macro = Macro(
                app_map_id=None,
                entity=None,
                name=c.name,
                description=c.description,
                trigger_patterns=c.trigger_patterns,
                parameters=c.parameters,
                macro_script=script,
                risk_tier=c.risk_tier,
                requires_confirmation=c.requires_confirmation,
                status="pending_review",
                is_active=False,
                namespace=NATIVE_NS,
                project_id=project_id,
                member_id=member_id,
            )
            db.add(macro)
            await db.flush()
            ids.append(macro.id)
    for macro_id in ids:
        await publish_macro_mutated(macro_id, action="create")
    logger.info("[native_factory] persisted %d native macros", len(ids))
    return ids
