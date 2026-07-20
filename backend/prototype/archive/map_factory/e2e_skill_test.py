"""E2E: 创建已验证技能 → 路由索引 → 执行, 全链路。"""
import asyncio, json, os, time
import httpx

BASE = "http://127.0.0.1:20160/api/v1"

MACRO_YAML = """
steps:
  # 1. 打开商品列表(未登录会被重定向到登录页)
  - step_number: 1
    type: action
    event_type: navigate
    source: dom
    payload:
      url: "http://127.0.0.1:9002/shop/goods/lists"
      wait_until: load

  - step_number: 2
    type: action
    event_type: wait
    source: dom
    payload:
      seconds: 2

  # 2. 登录态条件
  - step_number: 3
    type: if
    source: dom
    condition:
      type: element_exists
      target_selector: 'input[name="username"]'
    then_steps:
      - step_number: 31
        type: action
        event_type: type_text
        source: dom
        target_selector: 'input[name="username"]'
        payload:
          text: "{{mall_user}}"
      - step_number: 32
        type: action
        event_type: type_text
        source: dom
        target_selector: 'input[name="password"]'
        payload:
          text: "{{mall_pass}}"
      - step_number: 33
        type: action
        event_type: key_press
        source: dom
        payload:
          key: "Enter"
      - step_number: 34
        type: action
        event_type: wait
        source: dom
        payload:
          seconds: 4
      - step_number: 35
        type: action
        event_type: navigate
        source: dom
        payload:
          url: "http://127.0.0.1:9002/shop/goods/lists"
          wait_until: load
      - step_number: 36
        type: action
        event_type: wait
        source: dom
        payload:
          seconds: 2
    else_steps: []

  # 3. 搜索
  - step_number: 4
    type: action
    event_type: type_text
    source: dom
    target_selector: 'input[name="search_text"]'
    payload:
      text: "{{search}}"

  - step_number: 5
    type: action
    event_type: click
    source: dom
    target_selector: 'button[lay-filter="search"]'
    payload: {}

  - step_number: 6
    type: action
    event_type: wait
    source: dom
    payload:
      seconds: 3

  # 4. 读取结果
  - step_number: 7
    type: extract
    extract_type: get_text
    source: dom
    target_selector: .layui-table-main
    key: goods_table
"""

async def main():
    client = httpx.AsyncClient(base_url=BASE, timeout=60)

    # 1. 创建技能
    print("=== Step 1: 创建技能 from YAML ===")
    r = await client.post("/learning/skills/from-yaml", json={
        "name": "查询商品列表",
        "description": "在商城后台查询商品列表，自动处理登录态",
        "yaml_content": MACRO_YAML,
    })
    print("  status:", r.status_code)
    if r.status_code != 200:
        print("  body:", r.text[:500])
        return
    data = r.json()
    print("  response:", json.dumps(data, ensure_ascii=False, indent=2))
    skill_id = data.get("skill_id")
    if not skill_id:
        print("  ERROR: no skill_id!")
        return
    print(f"  ✅ Skill {skill_id} created (pending_review)")

    # 1b. 确认 skill (pending_review -> verified)
    print(f"\n=== Step 1b: 确认 Skill {skill_id} ===")
    r = await client.post(f"/learning/skills/{skill_id}/confirm")
    print("  status:", r.status_code)
    if r.status_code == 200:
        print("  ✅ Skill confirmed -> verified")
    else:
        print("  body:", r.text[:500])

    # 2. 等路由索引重建并确认技能已出现
    print("\n=== Step 2: 等待路由索引包含新技能 ===")
    for i in range(12):  # up to 60s
        await asyncio.sleep(5)
        r = await client.get("/route/index")
        if r.status_code == 200:
            idx = r.json()
            entries = idx.get('entries', [])
            found = any(e.get('id') == f'skill:{skill_id}' for e in entries)
            print(f"  attempt {i+1}: {idx.get('count')} entries, skill{skill_id} present={found}")
            if found:
                break

    # 3. 执行技能
    print(f"\n=== Step 3: 执行 Skill {skill_id} ===")
    r = await client.post(f"/learning/skills/{skill_id}/execute", json={
        "thread_id": "e2e-test-mall-list",
        "params": {
            "mall_user": "admin",
            "mall_pass": "admin888",
            "search": "订阅",
        }
    })
    print("  status:", r.status_code)
    print("  body:", r.text[:500])

    await client.aclose()
    print("\nDone. 看浏览器!")

if __name__ == "__main__":
    asyncio.run(main())
