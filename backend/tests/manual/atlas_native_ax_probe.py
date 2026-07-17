"""M1+ probe: AX coverage tiering for native-app Atlas (report/design M1).

For each target app: activate -> dump AX tree -> coverage metrics -> try
AXEnhancedUserInterface/AXManualAccessibility unlock -> re-dump -> compare.
For pilot apps: restart and measure (role,name,path) stability (Jaccard).

    .venv/bin/python tests/manual/atlas_native_ax_probe.py

NOTE: steals focus while running (activates each app in turn).
"""

import ast
import json
import subprocess
import sys
import time

sys.path.insert(0, "/Users/huangjinhuan/Projects/develop-assistant.cn/evoloop/backend")

import AppKit
import HIServices

APPS = [
    ("Calculator", "com.apple.calculator", True),
    ("System Settings", "com.apple.systempreferences", True),
    ("Music", "com.apple.Music", True),
    ("WeChat", "com.tencent.xinWeChat", True),
    ("Safari", "com.apple.Safari", False),
    ("Finder", "com.apple.finder", False),
    ("Terminal", "com.apple.Terminal", False),
    ("Notes", "com.apple.Notes", False),
    ("VSCode", "com.microsoft.VSCode", False),
]

INTERACTIVE_ROLES = {
    "AXButton", "AXTextField", "AXTextArea", "AXMenuItem", "AXMenuBarItem",
    "AXCheckBox", "AXRadioButton", "AXSlider", "AXPopUpButton", "AXComboBox",
    "AXTab", "AXTabGroup", "AXLink", "AXSwitch", "AXStepper", "AXSearchField",
    "AXIncrementor", "AXValueIndicator", "AXOutline", "AXTable", "AXRow",
}


def _running_app(bundle_id: str):
    for app in AppKit.NSWorkspace.sharedWorkspace().runningApplications():
        if app.bundleIdentifier() == bundle_id:
            return app
    return None


def _frontmost_bundle() -> str | None:
    app = AppKit.NSWorkspace.sharedWorkspace().frontmostApplication()
    return app.bundleIdentifier() if app else None


def _activate(bundle_id: str) -> bool:
    """Activate via AppleScript: `open -b`/NSRunningApplication.activate from a
    background process is ignored when a focus-sticky app (e.g. WeChat) holds
    the foreground; `tell application id ... to activate` is not."""
    if _frontmost_bundle() == bundle_id:
        return True
    if _running_app(bundle_id) is None:
        r = subprocess.run(["open", "-b", bundle_id], capture_output=True, timeout=15)
        if r.returncode != 0:
            return False
        deadline = time.time() + 10
        while time.time() < deadline and _running_app(bundle_id) is None:
            time.sleep(0.3)
    r = subprocess.run(
        ["osascript", "-e", f'tell application id "{bundle_id}" to activate'],
        capture_output=True,
        timeout=15,
    )
    if r.returncode != 0:
        return False
    deadline = time.time() + 8
    while time.time() < deadline:
        if _frontmost_bundle() == bundle_id:
            time.sleep(1.0)  # let the window settle
            return True
        time.sleep(0.3)
    return False


def _terminate(bundle_id: str) -> None:
    app = _running_app(bundle_id)
    if app is not None:
        app.terminate()
        deadline = time.time() + 5
        while time.time() < deadline and _running_app(bundle_id) is not None:
            time.sleep(0.3)


def _set_ax_enhancers(bundle_id: str) -> bool:
    app = _running_app(bundle_id)
    if app is None:
        return False
    el = HIServices.AXUIElementCreateApplication(app.processIdentifier())
    ok = False
    for attr in ("AXEnhancedUserInterface", "AXManualAccessibility"):
        err = HIServices.AXUIElementSetAttributeValue(el, attr, True)
        if err == 0:
            ok = True
    return ok


def _dump(bundle_id: str) -> list[dict]:
    from app.infrastructure.drivers.macos import macos_driver

    raw = macos_driver.dump_ax_tree()
    if not raw or "Error" in raw:
        return []
    try:
        data = ast.literal_eval(raw.replace("missing value", "None"))
    except (ValueError, SyntaxError):
        return []
    return data if isinstance(data, list) else []


def _metrics(elements: list[dict]) -> dict:
    total = len(elements)
    named = [e for e in elements if (e.get("name") or "").strip()]
    interactive = [e for e in elements if e.get("role") in INTERACTIVE_ROLES]
    interactive_named = [e for e in interactive if (e.get("name") or "").strip()]
    with_path = [e for e in elements if e.get("path")]
    zero_bounds = [e for e in elements if (e.get("bounds") or [0, 0, 0, 0])[2:] == [0, 0]]
    menu = [e for e in elements if e.get("role") in ("AXMenuItem", "AXMenuBarItem")]
    return {
        "total": total,
        "named": len(named),
        "interactive": len(interactive),
        "interactive_named": len(interactive_named),
        "with_path": len(with_path),
        "menu": len(menu),
        "zero_bounds_pct": round(100 * len(zero_bounds) / max(1, total)),
        "named_pct": round(100 * len(named) / max(1, total)),
    }


def _tier(m: dict) -> str:
    if m["interactive_named"] >= 15 and m["named_pct"] >= 30:
        return "A(完整)"
    if m["interactive_named"] >= 5 or m["menu"] >= 10:
        return "B(部分)"
    return "C(残缺)"


def _named_signature(elements: list[dict]) -> set[tuple]:
    return {
        (e.get("role", ""), (e.get("name") or "").strip(), e.get("path", ""))
        for e in elements
        if (e.get("name") or "").strip()
    }


def main() -> None:
    ws = AppKit.NSWorkspace.sharedWorkspace()
    front = ws.frontmostApplication()
    original = front.bundleIdentifier() if front else None

    print(f"{'应用':16}{'层级':8}{'total':>6}{'named%':>7}{'交互':>5}{'交互命名':>6}{'菜单':>5}{'path':>6}{'零bounds%':>9}  增强后交互命名")
    results = {}
    for name, bundle, _pilot in APPS:
        if not _activate(bundle):
            print(f"{name:16}  未安装/无法激活")
            continue
        base = _dump(bundle)
        m = _metrics(base)
        enhanced = ""
        if _set_ax_enhancers(bundle):
            time.sleep(0.5)
            m2 = _metrics(_dump(bundle))
            delta = m2["interactive_named"] - m["interactive_named"]
            enhanced = f"{m2['interactive_named']} ({'+' if delta >= 0 else ''}{delta})"
        else:
            enhanced = "开关被拒"
        results[bundle] = {"metrics": m, "elements": base}
        print(
            f"{name:16}{_tier(m):8}{m['total']:>6}{m['named_pct']:>6}%{m['interactive']:>5}"
            f"{m['interactive_named']:>6}{m['menu']:>5}{m['with_path']:>6}{m['zero_bounds_pct']:>8}%  {enhanced}"
        )

    # ── pilot: restart stability ──
    print("\n── ax_path 重启稳定性（pilot，(role,name,path) 三元组 Jaccard）──")
    for name, bundle, pilot in APPS:
        if not pilot or bundle not in results:
            continue
        sig1 = _named_signature(results[bundle]["elements"])
        _terminate(bundle)
        if not _activate(bundle):
            print(f"  {name:16} 重启失败")
            continue
        time.sleep(1.0)
        sig2 = _named_signature(_dump(bundle))
        union = sig1 | sig2
        j = len(sig1 & sig2) / max(1, len(union))
        print(f"  {name:16} Jaccard={j:.2f}  (首次 {len(sig1)} / 重启 {len(sig2)} 命名元素)")

    if original:
        subprocess.run(
            ["osascript", "-e", f'tell application id "{original}" to activate'],
            capture_output=True,
            timeout=15,
        )

    with open("/tmp/ax_probe_results.json", "w") as f:
        json.dump({k: v["metrics"] for k, v in results.items()}, f, ensure_ascii=False, indent=1)
    print("\n明细已存 /tmp/ax_probe_results.json")


if __name__ == "__main__":
    main()
