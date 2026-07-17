"""LLM-driven AppMap survey validation (real LLM + real source).

Feeds the app_map_analysis SKILL.md contract and REAL member-center source to
qwen-plus (DashScope key from ../.env), asks for the write_app_map payload,
then runs the full P4 chain: validate (schema + source spot-check) ->
write_app_map tool -> generate task -> macros in DB.

Run: .venv/bin/python tests/manual/test_atlas_llm_survey.py
"""

import asyncio
import json
import logging
import os
import re

logging.disable(logging.CRITICAL)

DB = "/var/folders/h7/llqy_6yj04g6t9ls9gk8kgzw0000gn/T/opencode/atlas_llm_survey.db"
os.environ["SQLITE_PATH"] = DB
if os.path.exists(DB):
    os.remove(DB)

BACKEND = "/Users/huangjinhuan/Projects/develop-assistant.cn/evoloop/backend"
MALL = "/Users/huangjinhuan/Projects/develop-assistant.cn/member-center/backend"
PROJECT_ID = 88


def read(path, max_lines=None):
    with open(path, encoding="utf-8", errors="ignore") as f:
        lines = f.readlines()
    if max_lines:
        lines = lines[:max_lines]
    return "".join(lines)


def read_numbered(path, max_lines=None):
    """Read file with 1-based line-number prefixes (what view_file shows the Agent)."""
    with open(path, encoding="utf-8", errors="ignore") as f:
        lines = f.readlines()
    if max_lines:
        lines = lines[:max_lines]
    return "".join(f"{i}: {line}" for i, line in enumerate(lines, 1))


async def llm_survey() -> dict:
    import httpx
    from dotenv import dotenv_values

    key = dotenv_values(f"{BACKEND}/../.env").get("DASHSCOPE_API_KEY")
    assert key, "DASHSCOPE_API_KEY missing in evoloop/.env"

    skill = read(f"{BACKEND}/app/config/skills/app_map_analysis/SKILL.md")
    controller = read_numbered(f"{MALL}/app/shop/controller/Goods.php", max_lines=800)
    list_html = read_numbered(f"{MALL}/app/shop/view/goods/lists.html")
    edit_html = read_numbered(f"{MALL}/app/shop/view/goods/edit_goods.html")
    goods_sql = read(f"{MALL}/b2c_mall.sql").split("CREATE TABLE `goods` (")[1][:1500]

    prompt = f"""{skill}

---

你现在调研一个 ThinkPHP 商城后台的 goods（商品）实体。下面是真实源码（每行已带真实行号前缀 `行号: 内容`，引用行号时直接抄前缀，不要自己数）。

=== 文件 app/shop/controller/Goods.php（前 800 行）===
{controller}

=== 文件 app/shop/view/goods/lists.html ===
{list_html}

=== 文件 app/shop/view/goods/edit_goods.html ===
{edit_html}

=== b2c_mall.sql 中 goods 表定义 ===
CREATE TABLE `goods` ({goods_sql}

---

要求：
1. 严格只输出一个 JSON 对象（不要 markdown 围栏、不要解释），字段：
   entity, platform, aliases, routes, actions, elements, db_tables
2. 每个 action 必须给 controller（相对路径）和 line（该 action 方法定义的真实行号）。
3. 每个 element 的 name 必须是页面源码中真实存在的符号（id/name/lay-filter 值），并给 page + line。
4. 覆盖你能在源码中找到的全部 CRUD action（lists/addGoods/editGoods/deleteGoods/getGoodsSkuList 等）。
5. routes 的 url 按 ThinkPHP 约定 /shop/goods/<action>，source_action 回指 action name。
6. 价格/库存写操作标 risk_tier=money。
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

    with open(
        "/var/folders/h7/llqy_6yj04g6t9ls9gk8kgzw0000gn/T/opencode/llm_survey_raw.txt",
        "w",
    ) as f:
        f.write(text)
    text = text.strip()
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text, flags=re.M).strip()
    start, end = text.find("{"), text.rfind("}")
    return json.loads(text[start : end + 1])


async def main():
    from app.infrastructure.database.resource_manager import db_resource_manager

    await db_resource_manager.initialize(create_tables=True, seed_data=False)

    print("[1] 调用 qwen-plus 调研真实源码（~2500 行）...")
    payload = await llm_survey()
    actions = payload.get("actions", [])
    elements = payload.get("elements", [])
    print(
        f"    LLM 产出: {len(actions)} actions, {len(elements)} elements, "
        f"{len(payload.get('routes', []))} routes, {len(payload.get('db_tables', []))} tables"
    )
    for a in actions:
        print(
            f"      - {a.get('name')} [{a.get('kind')}/{a.get('risk_tier')}] @ {a.get('controller')}:{a.get('line')}"
        )

    # ---------- validate against real source ----------
    from app.core.atlas.source.schemas import AppMapPayload
    from app.core.atlas.source.validate import validate_app_map

    p = AppMapPayload(**payload)
    problems = await validate_app_map(p, project_path=MALL)
    if problems:
        print(f"[2] 校验发现问题 ({len(problems)}):")
        for x in problems:
            print(f"      ! {x}")
    else:
        print("[2] validate_app_map: schema + 回源抽检全部通过（零幻觉）")

    # ---------- write via tool entry ----------
    from app.core.context.manager import ContextManager, EvoContext

    ctx = EvoContext(
        thread_id="thread-llm",
        project_id=PROJECT_ID,
        member_id=0,
        working_directory=MALL,
    )
    token = ContextManager.set(ctx)
    try:
        from app.core.tools.registry import get_tool_map

        write_tool = get_tool_map()["write_app_map"]
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
        print(f"[3] write_app_map → {str(res).splitlines()[0]}")
        saved = "saved as" in str(res) or "unchanged" in str(res)
        assert saved or problems, res

        if not saved:
            print("    （地图因校验问题未落库——验证了幻觉拦截链路）")
            return

        from app.core.atlas.source import persistence

        active = await persistence.get_active_app_map(PROJECT_ID, p.entity)

        # ---------- generate macros (task body) ----------
        import inspect

        from app.core.execution.macro import tasks as macro_tasks

        wrapped = macro_tasks.synthesize_macros_task
        raw = None
        fn = getattr(wrapped, "func", wrapped)
        if inspect.iscoroutinefunction(fn):
            raw = fn
        else:
            for cell in getattr(fn, "__closure__", None) or []:
                if inspect.iscoroutinefunction(cell.cell_contents):
                    raw = cell.cell_contents
                    break

        out = await raw(app_map_id=active.id, project_id=PROJECT_ID, member_id=0)
        print(
            f"[4] 模板厂: {out['candidates']} 候选宏, gaps={len(out['gaps'])}, errors={len(out['validation_errors'])}"
        )
        for g in out["gaps"]:
            print(f"      gap: {g}")
        for e in out["validation_errors"]:
            print(f"      err: {e}")

        from app.core.execution.macro import lifecycle

        macros = await lifecycle.list_macros(project_id=PROJECT_ID)
        for m in macros:
            print(f"      宏 #{m.id} {m.name} [{m.risk_tier}] status={m.status}")
    finally:
        ContextManager.reset(token)
        await db_resource_manager.shutdown()

    print("\n✅ LLM 真实调研链路完成")


asyncio.run(main())
