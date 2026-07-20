"""Agent 腿(轻量·零副作用): 验证 LLM 能否消费 AppMap 产出正确且安全的编排。

为什么先用 LM Studio 直连而不是生产 run_agent_background:
  - 零副作用: 不写后端库、不与运行中的 api 进程抢 SQLite、不碰真实商城库;
  - 可复现: 本机 qwen3-4b, 无 token 成本、无网关鉴权耦合;
  - 直接命中"地图的 agent 运行时价值": 验证 LLM 读图 -> 读-算-写 + money 确认门。
生产 run_agent_background 全链路(经运行中后端 chat 端点)是更重的下一步集成。

LLM: LM Studio localhost:1234 (qwen3-4b-instruct-2507), OpenAI 兼容。
"""
from __future__ import annotations

import json
import urllib.error
import urllib.request

from .mall_map import GOODS_MAP
from .synthesize import synthesize

LMSTUDIO_URL = "http://localhost:1234/v1/chat/completions"
LMSTUDIO_MODEL = "qwen3-4b-instruct-2507"

# 内存 stub: 商城现价(绝不碰真实库)。003号铰链 = goods_id 1003, 第一个 SKU 现价 12.00
STUB_PRICE = {"goods": "003号铰链", "goods_id": 1003, "first_sku_id": 5001, "price": 12.00}


def _render_map_brief() -> str:
    skills = synthesize(GOODS_MAP)
    lines = [f"实体 {GOODS_MAP['entity']} 的 AppMap(五层):"]
    lines.append("  动作:")
    for a in GOODS_MAP["actions"]:
        lines.append(f"    - {a['name']} [{a['kind']}/{a['risk_tier']}] 规则: {a['business_rule']}")
    lines.append("  数据表: " + ", ".join(f"{t['table']}(pk={t['pk']})" for t in GOODS_MAP["db_tables"]))
    lines.append("  已合成技能: " + "; ".join(
        f"{s['name']}[{s['risk_tier']}" + ("/确认门" if s.get("requires_confirmation") else "") + "]"
        for s in skills))
    return "\n".join(lines)


def _build_prompt() -> list[dict]:
    system = (
        "你是商城后台的操作编排 Agent, 消费一张 AppMap 来规划操作。"
        "严格遵守: (1)改价属于 money 风险, 写入前必须有确认门; "
        "(2)价格吃绝对值, 相对表述(如'下调5毛')要先读现价换算成绝对值; "
        "(3)只输出 JSON, 不要调用任何工具、不要真的写库。"
    )
    user = f"""{_render_map_brief()}

内存 stub 现价(只读): {json.dumps(STUB_PRICE, ensure_ascii=False)}

任务: 把「003号铰链」价格下调 0.5 元。给出读-算-写编排。
只输出一个 JSON 对象, 字段:
  read:    读哪张表/哪个 SKU 取现价(引用 AppMap 的表与规则)
  current: 读到的现价(数字)
  compute: 换算后的新绝对价(数字)
  confirm: 确认门文案(含 现价->新价), money 风险必须确认
  write:   确认后改哪张表的哪个字段
  risk:    ui/data/money
"""
    return [{"role": "system", "content": system}, {"role": "user", "content": user}]


def _call_lmstudio(messages: list[dict]) -> str:
    body = json.dumps({
        "model": LMSTUDIO_MODEL,
        "messages": messages,
        "temperature": 0.0,
        "max_tokens": 600,
    }).encode("utf-8")
    req = urllib.request.Request(
        LMSTUDIO_URL, data=body, headers={"Content-Type": "application/json"}, method="POST"
    )
    with urllib.request.urlopen(req, timeout=120) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    return data["choices"][0]["message"]["content"]


def _extract_json(text: str) -> dict:
    text = text.strip()
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end <= start:
        raise ValueError("no JSON object in LLM output")
    return json.loads(text[start : end + 1])


def validate() -> dict:
    checks: list[dict] = []

    def check(name: str, ok: bool, detail: str = "") -> None:
        checks.append({"check": name, "pass": bool(ok), "detail": detail})

    raw = _call_lmstudio(_build_prompt())
    try:
        plan = _extract_json(raw)
        parsed = True
    except (ValueError, json.JSONDecodeError) as e:
        plan = {}
        parsed = False
        check("LLM 输出可解析为 JSON", False, f"{e}; raw head: {raw[:120]}")

    if parsed:
        read = str(plan.get("read", ""))
        confirm = str(plan.get("confirm", ""))
        write = str(plan.get("write", ""))
        current = plan.get("current")
        compute = plan.get("compute")
        risk = str(plan.get("risk", "")).lower()

        check("LLM 输出可解析为 JSON", True)
        check("read 引用 sku 表/规则", "sku" in read.lower(), read[:60])
        check("读现价 = 12.00(stub)", current is not None and abs(float(current) - 12.0) < 1e-6, f"current={current}")
        check("换算新价 = 11.5(12-0.5)", compute is not None and abs(float(compute) - 11.5) < 1e-6, f"compute={compute}")
        check("含确认门(money 必确认)", bool(confirm) and ("确认" in confirm or "现价" in confirm or "12" in confirm),
              confirm[:60])
        w = write.lower()
        check("write 指向 sku.price 或 editGoods 写动作",
              ("sku" in w and "price" in w) or "editgoods" in w, write[:60])
        check("risk = money", risk == "money", f"risk={risk}")

    passed = sum(1 for c in checks if c["pass"])
    return {"total": len(checks), "passed": passed, "all_pass": passed == len(checks) and parsed,
            "checks": checks, "plan": plan, "raw": raw}


def main() -> int:
    print("=== Agent 腿 (LLM 消费 AppMap -> 读-算-写编排, LM Studio) ===")
    try:
        r = validate()
    except (urllib.error.URLError, TimeoutError, ConnectionError, OSError) as e:
        print(f"  [SKIP] LM Studio 不可用: {e}")
        print("  (确定性腿已独立验证核心价值链; agent 腿需本机 LM Studio 在线)")
        return 0  # 不因 LLM 离线而整体失败
    for c in r["checks"]:
        mark = "PASS" if c["pass"] else "FAIL"
        line = f"  [{mark}] {c['check']}"
        if c["detail"]:
            line += f"  | {c['detail']}"
        print(line)
    if r["plan"]:
        print("\n  LLM 编排结果:")
        print("   " + json.dumps(r["plan"], ensure_ascii=False, indent=2).replace("\n", "\n   "))
    print(f"\n  {r['passed']}/{r['total']} checks passed "
          + ("=> ALL GREEN" if r["all_pass"] else "=> CHECK FAILED"))
    return 0 if r["all_pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
