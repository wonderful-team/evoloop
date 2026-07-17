"""M1.5 probe: AX action primitive availability matrix (focus-free, background).

Answers the G2/G4 architecture question: can text be written WITHOUT focus
(AXSetValue on AXValue), or must key-in macros acquire focus (CGEvent)?

Method per target app (launched via `open -b`, never activated):
  1. Dump window elements by pid (no focus steal).
  2. Inventory: AXUIElementCopyActionNames per interesting role.
  3. Mutation tests (safe set only, original value restored):
     - text roles (AXTextField/AXTextArea/AXSearchField/AXComboBox):
       AXValue settable? -> set probe string -> read back -> restore.
     - AXPopUpButton: AXShowMenu -> AXCancel.
     - AXButton: AXPress only on Calculator digits (read-back via display).
     - AXSlider/AXStepper/AXCheckBox: inventory only (real settings risk).
  4. Verify frontmost app never changes (focus-free evidence).

    .venv/bin/python tests/manual/atlas_native_action_matrix.py
"""

import json
import subprocess
import sys
import time

sys.path.insert(0, "/Users/huangjinhuan/Projects/develop-assistant.cn/evoloop/backend")

import HIServices

from app.infrastructure.drivers.macos._workspace import (
    ax_copy_attribute,
    frontmost_application,
    running_pid_for_bundle,
)

TEXT_ROLES = {"AXTextField", "AXTextArea", "AXSearchField", "AXComboBox"}
INVENTORY_ONLY_ROLES = {"AXSlider", "AXStepper", "AXCheckBox", "AXSwitch", "AXRadioButton"}
PROBE_TEXT = "M15PROBE"
MAX_DEPTH = 12

TARGETS = [
    ("TextEdit", "com.apple.TextEdit"),
    ("Safari", "com.apple.Safari"),
    ("System Settings", "com.apple.systempreferences"),
    ("Music", "com.apple.Music"),
    ("Calculator", "com.apple.calculator"),
    ("WeChat", "com.tencent.xinWeChat"),
]


def _launch(bundle_id: str, wait: float = 20.0) -> int | None:
    next_open = 0.0
    deadline = time.time() + wait
    while time.time() < deadline:
        pid = running_pid_for_bundle(bundle_id)
        if pid is None:
            if time.time() >= next_open:
                subprocess.run(["open", "-b", bundle_id], capture_output=True, timeout=15)
                next_open = time.time() + 4.0
            time.sleep(0.3)
            continue
        if _windows(pid):
            time.sleep(0.5)
            return pid
        time.sleep(0.6)
    return running_pid_for_bundle(bundle_id)


def _app_el(pid: int):
    return HIServices.AXUIElementCreateApplication(pid)


def _windows(pid: int) -> list:
    return ax_copy_attribute(_app_el(pid), "AXWindows") or []


def _walk(el, depth: int, out: list) -> None:
    if depth > MAX_DEPTH:
        return
    out.append(el)
    for k in ax_copy_attribute(el, "AXChildren") or []:
        _walk(k, depth + 1, out)


def _actions(el) -> list[str]:
    err, names = HIServices.AXUIElementCopyActionNames(el, None)
    if err != 0 or names is None:
        return []
    return [str(n) for n in names]


def _settable(el, attr: str) -> bool:
    err, flag = HIServices.AXUIElementIsAttributeSettable(el, attr, None)
    return bool(flag) if err == 0 else False


def _front_bundle() -> str:
    app = frontmost_application()
    return app.bundleIdentifier() if app else "?"


def probe_app(name: str, bundle: str) -> dict:
    pid = _launch(bundle)
    if pid is None:
        return {"error": "launch failed"}
    els: list = []
    for w in _windows(pid):
        _walk(w, 0, els)
    inv: dict[str, set] = {}
    for e in els:
        role = ax_copy_attribute(e, "AXRole") or "?"
        for a in _actions(e):
            inv.setdefault(str(role), set()).add(a)

    result: dict = {
        "pid": pid,
        "elements": len(els),
        "action_inventory": {r: sorted(v) for r, v in sorted(inv.items())},
        "text_tests": [],
        "popup_tests": [],
        "press_tests": [],
    }

    # text write tests
    for e in els:
        role = str(ax_copy_attribute(e, "AXRole") or "")
        if role not in TEXT_ROLES:
            continue
        desc = ax_copy_attribute(e, "AXDescription") or ax_copy_attribute(e, "AXTitle") or ""
        settable = _settable(e, "AXValue")
        entry = {"role": role, "desc": str(desc)[:40], "settable": settable}
        if settable:
            original = ax_copy_attribute(e, "AXValue")
            err = HIServices.AXUIElementSetAttributeValue(e, "AXValue", PROBE_TEXT)
            time.sleep(0.3)
            readback = ax_copy_attribute(e, "AXValue")
            entry["set_err"] = err
            entry["readback_ok"] = isinstance(readback, str) and PROBE_TEXT in readback
            HIServices.AXUIElementSetAttributeValue(e, "AXValue", original if isinstance(original, str) else "")
            entry["restored"] = True
        result["text_tests"].append(entry)

    # popup AXShowMenu tests (show then cancel)
    for e in els:
        role = str(ax_copy_attribute(e, "AXRole") or "")
        if role != "AXPopUpButton":
            continue
        acts = _actions(e)
        entry = {"actions": acts}
        if "AXShowMenu" in acts:
            err = HIServices.AXUIElementPerformAction(e, "AXShowMenu")
            time.sleep(0.4)
            entry["show_err"] = err
            HIServices.AXUIElementPerformAction(e, "AXCancel")
            entry["cancel_attempted"] = True
        result["popup_tests"].append(entry)

    # Calculator digit press read-back (safe arithmetic proof)
    if bundle == "com.apple.calculator":
        def find_button(label: str):
            for e in els:
                if str(ax_copy_attribute(e, "AXRole") or "") != "AXButton":
                    continue
                for a in ("AXDescription", "AXTitle"):
                    if ax_copy_attribute(e, a) == label:
                        return e
            return None

        seq = ["全部清除", "4", "乘", "5", "等于"]
        ok = True
        for label in seq:
            btn = find_button(label)
            if btn is None:
                result["press_tests"].append({"label": label, "missing": True})
                ok = False
                break
            HIServices.AXUIElementPerformAction(btn, "AXPress")
            time.sleep(0.3)
        if ok:
            els2: list = []
            for w in _windows(pid):
                _walk(w, 0, els2)
            texts = [
                str(ax_copy_attribute(e, "AXValue") or "")
                for e in els2
                if str(ax_copy_attribute(e, "AXRole") or "") == "AXStaticText"
            ]
            result["press_tests"].append({"seq": "4×5", "display": [t for t in texts if t.strip()]})

    return result


def main() -> None:
    front0 = _front_bundle()
    print(f"frontmost before: {front0}\n")
    all_results: dict[str, dict] = {}
    for name, bundle in TARGETS:
        r = probe_app(name, bundle)
        all_results[bundle] = r
        front_now = _front_bundle()
        focus_ok = "OK" if front_now == front0 else f"CHANGED->{front_now}"
        print(f"── {name} ({bundle}) pid={r.get('pid')} elements={r.get('elements')} focus:{focus_ok}")
        if "error" in r:
            print(f"   {r['error']}")
            continue
        for t in r["text_tests"]:
            if t["settable"]:
                print(
                    f"   TEXT {t['role']} {t['desc']!r}: settable=1 set_err={t['set_err']} "
                    f"readback={'PASS' if t['readback_ok'] else 'FAIL'} restored={t['restored']}"
                )
            else:
                print(f"   TEXT {t['role']} {t['desc']!r}: settable=0")
        for p in r["popup_tests"]:
            print(f"   POPUP actions={p['actions']} show_err={p.get('show_err')}")
        for p in r["press_tests"]:
            print(f"   PRESS {p}")
        interesting = {
            r_: a for r_, a in r["action_inventory"].items()
            if r_ in TEXT_ROLES | INVENTORY_ONLY_ROLES | {"AXPopUpButton", "AXButton", "AXMenuItem"}
        }
        for r_, acts in interesting.items():
            print(f"   INV {r_}: {acts}")

    with open("/tmp/ax_action_matrix.json", "w") as f:
        json.dump(all_results, f, ensure_ascii=False, indent=1, default=str)
    print(f"\nfrontmost after: {_front_bundle()}")
    print("明细已存 /tmp/ax_action_matrix.json")


if __name__ == "__main__":
    main()
