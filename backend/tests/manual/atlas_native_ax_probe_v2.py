"""M1 probe v2: FOCUS-FREE AX survey via AXUIElementCreateApplication(pid).

v1 lesson: activation from a background process is unreliable (cross-Space
focus stealing is silently blocked; some apps hold focus). The frontmost-only
limitation of macos_driver.dump_ax_tree is a driver artifact, NOT an AX API
limitation — any running app's tree can be dumped by pid without touching
focus.

v2 lessons (baked into launch recipe):
- `open -g` is unreliable: apps may not even report running, and windows are
  never materialized. Plain `open -b` DOES materialize windows even when the
  activation itself is focus-blocked — poll for windows, not just pid.
- NSRunningApplication.terminate() can silently no-op; use forceTerminate
  fallback.
- AXPress on background apps is VERIFIED working (Calculator 3×3=9 read back
  from AXStaticText while VSCode stayed frontmost) — focus is needed only
  for CGEvent keyboard injection, NOT for surveying or AXPress interaction.

    .venv/bin/python tests/manual/atlas_native_ax_probe_v2.py
"""

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
MAX_DEPTH = 12


def _exe_path(bundle_id: str) -> str | None:
    url = AppKit.NSWorkspace.sharedWorkspace().URLForApplicationWithBundleIdentifier_(bundle_id)
    if url is None:
        return None
    bundle = AppKit.NSBundle.bundleWithURL_(url)
    exe = bundle.executableURL() if bundle is not None else None
    return exe.path() if exe is not None else None


def _running_pid(bundle_id: str) -> int | None:
    """pgrep-based: NSWorkspace.runningApplications() is a notification-fed
    snapshot that never refreshes in a process without a spinning runloop."""
    exe = _exe_path(bundle_id)
    if not exe:
        return None
    r = subprocess.run(["pgrep", "-f", exe], capture_output=True, timeout=10)
    if r.returncode != 0:
        return None
    out = r.stdout.decode().split()
    return int(out[0]) if out else None


def _launch_bg(bundle_id: str, wait_windows: float = 20.0) -> bool:
    """`open -b` (retried — LaunchServices throttles relaunch right after a
    forceTerminate) + poll until windows materialize (focus not required)."""
    next_open = 0.0
    deadline = time.time() + wait_windows
    while time.time() < deadline:
        if _running_pid(bundle_id) is None:
            if time.time() >= next_open:
                subprocess.run(["open", "-b", bundle_id], capture_output=True, timeout=15)
                next_open = time.time() + 4.0
            time.sleep(0.3)
            continue
        if _dump_pid(bundle_id)["windows"]:
            time.sleep(0.5)
            return True
        time.sleep(0.6)
    return _running_pid(bundle_id) is not None


def _ax_get(el, attr):
    err, val = HIServices.AXUIElementCopyAttributeValue(el, attr, None)
    if err != 0:
        return None
    return val


def _ax_point_size(el) -> list[int]:
    bounds = [0, 0, 0, 0]
    pos = _ax_get(el, "AXPosition")
    size = _ax_get(el, "AXSize")
    try:
        if pos is not None:
            ok, pt = HIServices.AXValueGetValue(pos, HIServices.kAXValueCGPointType, None)
            if ok:
                bounds[0], bounds[1] = int(pt.x), int(pt.y)
        if size is not None:
            ok, sz = HIServices.AXValueGetValue(size, HIServices.kAXValueCGSizeType, None)
            if ok:
                bounds[2], bounds[3] = int(sz.width), int(sz.height)
    except (TypeError, ValueError):
        pass
    return bounds


def _walk(el, path: str, depth: int, out: list[dict]) -> None:
    if depth > MAX_DEPTH:
        return
    role = _ax_get(el, "AXRole") or "AXUnknown"
    name = _ax_get(el, "AXTitle") or _ax_get(el, "AXDescription") or _ax_get(el, "AXValue") or ""
    bounds = _ax_point_size(el)
    out.append({"role": str(role), "name": str(name) if name else "", "path": path, "bounds": bounds})
    children = _ax_get(el, "AXChildren") or []
    for i, child in enumerate(children):
        _walk(child, f"{path} > {role} {i + 1}", depth + 1, out)


def _dump_pid(bundle_id: str) -> dict[str, list[dict]]:
    """Returns {'menubar': [...], 'windows': [...]} — menubar is reliably rich
    on macOS even for AX-poor apps (WeChat); content must be scored apart."""
    pid = _running_pid(bundle_id)
    if pid is None:
        return {"menubar": [], "windows": []}
    app_el = HIServices.AXUIElementCreateApplication(pid)
    bar: list[dict] = []
    menu_bar = _ax_get(app_el, "AXMenuBar")
    if menu_bar is not None:
        _walk(menu_bar, "menubar", 0, bar)
    wins: list[dict] = []
    windows = _ax_get(app_el, "AXWindows") or []
    for i, w in enumerate(windows):
        _walk(w, f"window {i + 1}", 0, wins)
    return {"menubar": bar, "windows": wins}


def _activate_foreground(bundle_id: str) -> bool:
    """open + osascript activate with verify+retry (cross-Space focus stealing
    can silently fail; apps launched hidden create no windows)."""
    for _attempt in range(3):
        subprocess.run(["open", "-b", bundle_id], capture_output=True, timeout=15)
        subprocess.run(
            ["osascript", "-e", f'tell application id "{bundle_id}" to activate'],
            capture_output=True,
            timeout=15,
        )
        deadline = time.time() + 6
        while time.time() < deadline:
            AppKit.NSRunLoop.currentRunLoop().runUntilDate_(
                AppKit.NSDate.dateWithTimeIntervalSinceNow_(0.3)
            )
            app = AppKit.NSWorkspace.sharedWorkspace().frontmostApplication()
            if app and app.bundleIdentifier() == bundle_id:
                time.sleep(1.2)
                return True
            time.sleep(0.3)
    return False


def _set_ax_enhancers(bundle_id: str) -> bool:
    pid = _running_pid(bundle_id)
    if pid is None:
        return False
    el = HIServices.AXUIElementCreateApplication(pid)
    ok = False
    for attr in ("AXEnhancedUserInterface", "AXManualAccessibility"):
        if HIServices.AXUIElementSetAttributeValue(el, attr, True) == 0:
            ok = True
    return ok


def _metrics(elements: list[dict]) -> dict:
    total = len(elements)
    named = [e for e in elements if e["name"].strip()]
    interactive = [e for e in elements if e["role"] in INTERACTIVE_ROLES]
    interactive_named = [e for e in interactive if e["name"].strip()]
    menu = [e for e in elements if e["role"] in ("AXMenuItem", "AXMenuBarItem")]
    zero = [e for e in elements if e["bounds"][2:] == [0, 0]]
    return {
        "total": total,
        "named_pct": round(100 * len(named) / max(1, total)),
        "interactive": len(interactive),
        "interactive_named": len(interactive_named),
        "menu": len(menu),
        "zero_bounds_pct": round(100 * len(zero) / max(1, total)),
    }


def _tier(m: dict) -> str:
    if m["interactive_named"] >= 15 and m["named_pct"] >= 30:
        return "A(完整)"
    if m["interactive_named"] >= 5 or m["menu"] >= 10:
        return "B(部分)"
    return "C(残缺)"


def _sig(elements: list[dict]) -> set[tuple]:
    return {(e["role"], e["name"].strip(), e["path"]) for e in elements if e["name"].strip()}


def _terminate(bundle_id: str) -> None:
    exe = _exe_path(bundle_id)
    if exe:
        subprocess.run(["pkill", "-f", exe], capture_output=True, timeout=10)
    deadline = time.time() + 6
    while time.time() < deadline and _running_pid(bundle_id) is not None:
        time.sleep(0.3)


def main() -> None:
    print(
        f"{'应用':16}{'层级':8}{'窗口total':>8}{'命名%':>6}{'交互':>5}{'交互命名':>6}"
        f"{'零bounds%':>9}{'菜单':>6}  增强后窗口交互命名"
    )
    results: dict[str, dict] = {}
    for name, bundle, _pilot in APPS:
        if not _launch_bg(bundle):
            print(f"{name:16}  未安装/无法启动")
            continue
        base = _dump_pid(bundle)
        if not base["windows"]:
            _activate_foreground(bundle)
            base = _dump_pid(bundle)
        if not base["windows"] and not base["menubar"]:
            print(f"{name:16}  窗口未实体化")
            continue
        wm = _metrics(base["windows"])
        mm = _metrics(base["menubar"])
        if _set_ax_enhancers(bundle):
            time.sleep(0.5)
            m2 = _metrics(_dump_pid(bundle)["windows"])
            delta = m2["interactive_named"] - wm["interactive_named"]
            enhanced = f"{m2['interactive_named']} ({'+' if delta >= 0 else ''}{delta})"
        else:
            enhanced = "开关不适用"
        results[bundle] = {"windows": wm, "menubar": mm, "elements": base}
        print(
            f"{name:16}{_tier(wm):8}{wm['total']:>8}{wm['named_pct']:>5}%{wm['interactive']:>5}"
            f"{wm['interactive_named']:>6}{wm['zero_bounds_pct']:>8}%{mm['interactive_named']:>6}  {enhanced}"
        )

    print("\n── ax_path 重启稳定性（pilot，窗口区 (role,name,path) Jaccard）──")
    for name, bundle, pilot in APPS:
        if not pilot or bundle not in results:
            continue
        sig1 = _sig(results[bundle]["elements"]["windows"])
        _terminate(bundle)
        time.sleep(2.0)
        if not _launch_bg(bundle):
            print(f"  {name:16} 重启失败")
            continue
        dump2 = _dump_pid(bundle)
        if not dump2["windows"]:
            _activate_foreground(bundle)
            dump2 = _dump_pid(bundle)
        sig2 = _sig(dump2["windows"])
        union = sig1 | sig2
        j = len(sig1 & sig2) / max(1, len(union))
        print(f"  {name:16} Jaccard={j:.2f}  (首次 {len(sig1)} / 重启 {len(sig2)} 命名元素)")

    with open("/tmp/ax_probe_v2_results.json", "w") as f:
        json.dump({k: {"windows": v["windows"], "menubar": v["menubar"]} for k, v in results.items()}, f, ensure_ascii=False, indent=1)
    print("\n明细已存 /tmp/ax_probe_v2_results.json")


if __name__ == "__main__":
    main()
