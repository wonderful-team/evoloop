"""Wide-coverage AppMap generation across member-center entities.

For each core business entity: LLM surveys the real source (controller + views
+ table DDL with line numbers) -> validate (schema + source spot-check) ->
write_app_map tool -> template factory -> pending_review macros.

Run: .venv/bin/python tests/manual/test_atlas_wide_coverage.py
"""
import asyncio
import json
import logging
import os
import re
import time

logging.disable(logging.CRITICAL)

DB = "/var/folders/h7/llqy_6yj04g6t9ls9gk8kgzw0000gn/T/opencode/atlas_wide.db"
os.environ["SQLITE_PATH"] = DB
if os.path.exists(DB):
    os.remove(DB)

BACKEND = "/Users/huangjinhuan/Projects/develop-assistant.cn/evoloop/backend"
MALL = "/Users/huangjinhuan/Projects/develop-assistant.cn/member-center/backend"
PROJECT_ID = 88

ENTITIES = [
    {"entity": "goods", "controller": "Goods.php", "view_dir": "goods", "tables": ["goods", "goods_sku", "goods_category"]},
    {"entity": "order", "controller": "Order.php", "view_dir": "order", "tables": ["order", "order_goods", "order_common"]},
    {"entity": "orderrefund", "controller": "Orderrefund.php", "view_dir": "orderrefund", "tables": ["order_refund"]},
    {"entity": "member", "controller": "Member.php", "view_dir": "member", "tables": ["member", "member_level"]},
    {"entity": "memberlevel", "controller": "Memberlevel.php", "view_dir": "memberlevel", "tables": ["member_level"]},
    {"entity": "goodscategory", "controller": "Goodscategory.php", "view_dir": "goodscategory", "tables": ["goods_category"]},
    {"entity": "goodsbrand", "controller": "Goodsbrand.php", "view_dir": "goodsbrand", "tables": ["goods_brand"]},
    {"entity": "goodslabel", "controller": "Goodslabel.php", "view_dir": "goodslabel", "tables": ["goods_label"]},
    {"entity": "store", "controller": "Store.php", "view_dir": "store", "tables": ["store"]},
    {"entity": "promotion", "controller": "Promotion.php", "view_dir": "promotion", "tables": ["promotion"]},
]


def read_numbered(path, max_lines=None):
    try:
        with open(path, encoding="utf-8", errors="ignore") as f:
            lines = f.readlines()
    except OSError:
        return ""
    if max_lines:
        lines = lines[:max_lines]
    return "".join(f"{i}: {line}" for i, line in enumerate(lines, 1))


def pick_view_files(view_dir):
    """Pick the most template-relevant view files: list + add/edit pages."""
    base = os.path.join(MALL, "app/shop/view", view_dir)
    if not os.path.isdir(base):
        return []
    files = os.listdir(base)
    picked = []
    for pat in ("lists.html", "list.html", "index.html"):
        if pat in files:
            picked.append(pat)
            break
    for f in sorted(files):
        if f.endswith(".html") and (f.startswith("edit") or f.startswith("add")):
            picked.append(f)
            break
    return picked


def extract_table_ddl(sql_text, table):
    marker = f"CREATE TABLE `{table}` ("
    idx = sql_text.find(marker)
    if idx < 0:
        return ""
    return sql_text[idx : idx + 1200]


async def llm_call(key, skill, entity_cfg, sources):
    import httpx

    prompt = f"""{skill}

---

你现在调研一个 ThinkPHP 商城后台的 {entity_cfg['entity']} 实体。下面是真实源码（每行已带真实行号前缀 `行号: 内容`，引用行号时直接抄前缀，不要自己数）。

{sources}

---

要求：
1. 严格只输出一个 JSON 对象（不要 markdown 围栏、不要解释），字段：
   entity, platform, aliases, routes, actions, elements, db_tables
2. 每个 action 必须给 controller（相对路径）和 line（该 action 方法定义的真实行号）。
3. 每个 element 的 name 必须是页面源码中真实存在的符号（id/name/lay-filter 值），并给 page + line；
   必须收录：列表页搜索框、结果表格、表单页保存/提交按钮、写操作涉及的输入字段。
4. 覆盖你能在源码中找到的全部 CRUD action。
5. routes 的 url 按 ThinkPHP 约定 /shop/{entity_cfg['entity']}/<action>，source_action 回指 action name。
6. 价格/库存/余额/退款写操作标 risk_tier=money。
7. entity 用 "{entity_cfg['entity']}"，aliases 含中文业务名。
"""
    async with httpx.AsyncClient(timeout=300) as c:
        r = await c.post(
            "https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions",
            headers={"Authorization": f"Bearer {key}"},
            json={
                "model": "qwen-plus",
                "messages": [{"role": "user", "content": prompt}],
                "max_tokens": 8000,
                "temperature": 0.1,
            },
        )
        r.raise_for_status()
        text = r.json()["choices"][0]["message"]["content"]
    text = text.strip()
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text, flags=re.M).strip()
    return json.loads(text[text.find("{") : text.rfind("}") + 1])


async def main():
    from dotenv import dotenv_values

    key = dotenv_values(f"{BACKEND}/../.env").get("DASHSCOPE_API_KEY")
    assert key, "DASHSCOPE_API_KEY missing"

    from app.infrastructure.database.resource_manager import db_resource_manager

    await db_resource_manager.initialize(create_tables=True, seed_data=False)

    skill = open(f"{BACKEND}/app/config/skills/app_map_analysis/SKILL.md", encoding="utf-8").read()
    sql_text = open(f"{MALL}/b2c_mall.sql", encoding="utf-8", errors="ignore").read()

    from app.core.context.manager import ContextManager, EvoContext

    ctx = EvoContext(thread_id="thread-wide", project_id=PROJECT_ID, member_id=0, working_directory=MALL)
    token = ContextManager.set(ctx)

    report = []
    try:
        from app.core.atlas.source import persistence
        from app.core.atlas.source.schemas import AppMapPayload
        from app.core.atlas.source.validate import validate_app_map
        from app.core.tools.registry import get_tool_map

        write_tool = get_tool_map()["write_app_map"]

        import inspect

        from app.core.execution.macro import tasks as macro_tasks

        fn = getattr(macro_tasks.synthesize_macros_task, "func", macro_tasks.synthesize_macros_task)
        task_body = fn
        if not inspect.iscoroutinefunction(task_body):
            for cell in getattr(fn, "__closure__", None) or []:
                if inspect.iscoroutinefunction(cell.cell_contents):
                    task_body = cell.cell_contents
                    break

        for cfg in ENTITIES:
            t0 = time.time()
            entity = cfg["entity"]
            controller_path = f"app/shop/controller/{cfg['controller']}"
            controller = read_numbered(os.path.join(MALL, controller_path), max_lines=900)
            if not controller:
                report.append((entity, "SKIP: no controller", 0, 0, 0, 0))
                continue

            sources = f"=== 文件 {controller_path}（前 900 行）===\n{controller}\n"
            for vf in pick_view_files(cfg["view_dir"]):
                rel = f"app/shop/view/{cfg['view_dir']}/{vf}"
                content = read_numbered(os.path.join(MALL, rel), max_lines=800)
                if content:
                    sources += f"\n=== 文件 {rel} ===\n{content}\n"
            for tbl in cfg["tables"]:
                ddl = extract_table_ddl(sql_text, tbl)
                if ddl:
                    sources += f"\n=== b2c_mall.sql 表 {tbl} ===\n{ddl}\n"

            try:
                payload = await llm_call(key, skill, cfg, sources)
            except (json.JSONDecodeError, ValueError, KeyError) as e:
                report.append((entity, f"LLM输出解析失败: {e}", 0, 0, 0, 0))
                continue

            try:
                p = AppMapPayload(**payload)
            except (ValueError, TypeError) as e:
                report.append((entity, f"schema拒绝: {str(e)[:80]}", len(payload.get("actions", [])), 0, 0, 0))
                continue

            problems = await validate_app_map(p, project_path=MALL)
            if problems:
                report.append((entity, f"抽检拒绝({len(problems)}): {problems[0][:50]}", len(p.actions), 0, 0, 0))
                continue

            res = await write_tool.ainvoke(
                {
                    "entity": p.entity,
                    "platform": p.platform,
                    "aliases": p.aliases,
                    "routes": [r.model_dump() for r in p.routes],
                    "actions": [a.model_dump() for a in p.actions],
                    "elements": [e.model_dump() for e in p.elements],
                    "db_tables": [t.model_dump() for t in p.db_tables],
                }
            )
            if "saved as" not in str(res) and "unchanged" not in str(res):
                report.append((entity, f"写入失败: {str(res)[:60]}", len(p.actions), 0, 0, 0))
                continue

            active = await persistence.get_active_app_map(PROJECT_ID, p.entity)
            out = await task_body(app_map_id=active.id, project_id=PROJECT_ID, member_id=0)
            dt = time.time() - t0
            report.append(
                (entity, "OK", len(p.actions), len(p.elements), out["candidates"], len(out["gaps"]), round(dt))
            )
    finally:
        ContextManager.reset(token)

    print("\n" + "=" * 78)
    print(f"{'entity':<16} {'结果':<34} {'act':>4} {'elem':>5} {'宏':>4} {'gap':>4} {'秒':>5}")
    print("-" * 78)
    total_maps = total_macros = 0
    for row in report:
        entity, status = row[0], row[1]
        if status == "OK":
            _, _, na, ne, nc, ng, dt = row
            total_maps += 1
            total_macros += nc
            print(f"{entity:<16} {'OK':<34} {na:>4} {ne:>5} {nc:>4} {ng:>4} {dt:>5}")
        else:
            print(f"{entity:<16} {status[:34]:<34}")
    print("-" * 78)
    print(f"合计: {total_maps} 张地图, {total_macros} 个候选宏（pending_review）")

    await db_resource_manager.shutdown()


asyncio.run(main())
