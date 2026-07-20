"""确定性验证(无 LLM, 无后端): 校验工厂产出的技能正确 + 安全。

验证草案的核心主张:
  1. map -> 模板实例化 -> 技能(价值链 §7.8 闭环, 三动作全合成)
  2. 宏步骤合法: 坐标归一化(0~1)、element_name 优先(§7.2 坐标合同)、含 observe 校验步
  3. family 派生正确且 VOICE 可回放: 宏族 ⊆ {act,control,observe}, 无 escape(§7.2/§7.3)
  4. risk 门控: money 必带确认门; ui/data 免确认、纯 L1 可回放(§10.1/A2)
  5. 版本耦合: source_map_version 已盖章(§7.9)
  6. 参数绝对值: 写值引用绝对参数, 禁止相对表达式(§10.3/§11.3)
"""
from __future__ import annotations

from .families import derive_family, macro_families, voice_replayable
from .mall_map import GOODS_MAP
from .synthesize import synthesize


def _is_normalized(v) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool) and 0.0 <= v <= 1.0


def validate() -> dict:
    checks: list[dict] = []

    def check(name: str, ok: bool, detail: str = "") -> None:
        checks.append({"check": name, "pass": bool(ok), "detail": detail})

    skills = synthesize(GOODS_MAP)
    by_form = {s["skill_form"]: s for s in skills}

    # 1. 价值链闭环: 三动作全合成
    check("map->技能: 合成产出非空", len(skills) >= 1, f"{len(skills)} skills")
    check("map->技能: 三动作全合成", len(skills) == len(GOODS_MAP["actions"]),
          f"{len(skills)}/{len(GOODS_MAP['actions'])}")

    # 2. 宏步骤合法
    macro = by_form.get("macro")
    if macro:
        steps = macro["macro_script"]
        coord_steps = [st for st in steps if "x" in st.get("payload", {})]
        coord_ok = all(_is_normalized(st["payload"]["x"]) and _is_normalized(st["payload"]["y"])
                       for st in coord_steps)
        check("宏: 坐标全部归一化(0~1)", coord_ok and bool(coord_steps), f"{len(coord_steps)} 个坐标步")
        click = next((st for st in steps if st["event_type"] == "click"), None)
        check("宏: click 优先 element_name", click is not None and bool(click.get("target_selector")),
              f"selector={click.get('target_selector') if click else None}")
        has_observe = any(derive_family(st) == "observe" for st in steps)
        check("宏: 含 observe 校验步", has_observe, "extract/get_text 读结果")
        # 3. family 派生 + VOICE 回放门
        fams = macro_families(steps)
        check("宏: family 派生 ⊆ {act,observe}", fams <= {"act", "observe"}, f"families={sorted(fams)}")
        check("宏: VOICE 可回放(无 escape)", voice_replayable(steps))
    else:
        check("宏: list_view 已生成", False, "未生成宏")

    # 3b. 单逻辑技能 family
    if "native_read" in by_form:
        check("crud_read: family=observe", by_form["native_read"]["family"] == "observe")
    if "native_write" in by_form:
        check("crud_write: family=act", by_form["native_write"]["family"] == "act")

    # 4. risk 门控
    if "native_write" in by_form:
        w = by_form["native_write"]
        check("risk: money 技能带确认门", w["risk_tier"] == "money" and w.get("requires_confirmation") is True)
    ui_data_ok = (
        by_form.get("macro", {}).get("risk_tier") in ("ui", "data")
        and not by_form.get("macro", {}).get("requires_confirmation")
        and by_form.get("native_read", {}).get("risk_tier") == "data"
        and not by_form.get("native_read", {}).get("requires_confirmation")
    )
    check("risk: ui/data 免确认(纯 L1 可回放)", ui_data_ok)

    # 5. 版本耦合
    check("版本耦合: source_map_version 已盖章",
          bool(skills) and all(s.get("source_map_version") == GOODS_MAP["map_version"] for s in skills))

    # 6. 参数绝对值
    if "native_write" in by_form:
        w = by_form["native_write"]
        np = next((p for p in w["parameters"] if p["name"] == "new_price"), None)
        check("参数: new_price 为绝对值(number)", np is not None and np["type"] == "number")
        check("参数: 写值引用绝对参数(非相对表达式)", w["write_spec"]["set"]["price"] == "{{new_price}}",
              f"set.price={w['write_spec']['set']['price']}")

    passed = sum(1 for c in checks if c["pass"])
    return {
        "total": len(checks),
        "passed": passed,
        "all_pass": passed == len(checks),
        "checks": checks,
        "skills": skills,
    }


def main() -> int:
    r = validate()
    print("=== 确定性验证 (map -> 技能工厂 -> 校验) ===")
    for c in r["checks"]:
        mark = "PASS" if c["pass"] else "FAIL"
        line = f"  [{mark}] {c['check']}"
        if c["detail"]:
            line += f"  | {c['detail']}"
        print(line)
    print(f"\n  {r['passed']}/{r['total']} checks passed "
          + ("=> ALL GREEN" if r["all_pass"] else "=> FAILURES"))
    print("\n  生成的技能:")
    for s in r["skills"]:
        print(f"    - {s['name']}  [{s['skill_form']}/{s['risk_tier']}"
              + ("/确认门" if s.get("requires_confirmation") else "") + "]")
    return 0 if r["all_pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
