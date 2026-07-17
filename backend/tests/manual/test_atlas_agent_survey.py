"""Wide-coverage survey: agent-driven, per-entity independent tasks.

Architecture per design (单实体调研独立 Agent 任务):
  Phase A: the LLM discovers business entities itself by listing the
           controller directory (no hardcoded entity list).
  Phase B: one FRESH conversation per entity — the model explores with the
           repo's real registered tools (list_dir/grep_search/read_file) and
           calls the real write_app_map / generate_macros_from_app_map.
A repetition guard breaks identical-query loops.

Run: .venv/bin/python tests/manual/test_atlas_agent_survey.py
"""
import asyncio
import json
import logging
import os
import re

logging.disable(logging.CRITICAL)

DB = "/var/folders/h7/llqy_6yj04g6t9ls9gk8kgzw0000gn/T/opencode/atlas_agent.db"
os.environ["SQLITE_PATH"] = DB
if os.path.exists(DB):
    os.remove(DB)

BACKEND = "/Users/huangjinhuan/Projects/develop-assistant.cn/evoloop/backend"
MALL = "/Users/huangjinhuan/Projects/develop-assistant.cn/member-center/backend"
PROJECT_ID = 88
MAX_TURNS_PER_ENTITY = 25

TOOL_SCHEMAS = [
    {
        "type": "function",
        "function": {
            "name": "list_dir",
            "description": "List files and directories at a path (relative to project root).",
            "parameters": {
                "type": "object",
                "properties": {"path": {"type": "string"}},
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "grep_search",
            "description": "Search file contents with a regex pattern; returns matches with file:line.",
            "parameters": {
                "type": "object",
                "properties": {
                    "pattern": {"type": "string"},
                    "path": {"type": "string"},
                },
                "required": ["pattern"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "read_file",
            "description": "Read a file's content (with line numbers).",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string"},
                    "start_line": {"type": "integer"},
                    "end_line": {"type": "integer"},
                },
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "write_app_map",
            "description": "Save the surveyed AppMap for one entity (validated against source).",
            "parameters": {
                "type": "object",
                "properties": {
                    "entity": {"type": "string"},
                    "platform": {"type": "string"},
                    "aliases": {"type": "array", "items": {"type": "string"}},
                    "routes": {"type": "array", "items": {"type": "object"}},
                    "actions": {"type": "array", "items": {"type": "object"}},
                    "elements": {"type": "array", "items": {"type": "object"}},
                    "db_tables": {"type": "array", "items": {"type": "object"}},
                },
                "required": ["entity", "platform", "aliases", "routes", "actions", "elements", "db_tables"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "generate_macros_from_app_map",
            "description": "Run the template factory for a saved AppMap; produces pending_review macros.",
            "parameters": {
                "type": "object",
                "properties": {"app_map_id": {"type": "integer"}},
                "required": ["app_map_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "finish",
            "description": "Call when THIS entity is fully done (map written + macros generated, or given up with reason).",
            "parameters": {
                "type": "object",
                "properties": {"summary": {"type": "string"}},
                "required": ["summary"],
            },
        },
    },
]


class AgentRunner:
    def __init__(self, key, tool_map, task_body):
        self.key = key
        self.tool_map = tool_map
        self.task_body = task_body
        self.http = httpx.AsyncClient(timeout=300)

    async def close(self):
        await self.http.aclose()

    async def llm(self, messages, tools=None):
        body = {
            "model": "qwen-plus",
            "messages": messages,
            "temperature": 0.1,
        }
        if tools:
            body["tools"] = tools
            body["tool_choice"] = "auto"
        r = await self.http.post(
            "https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions",
            headers={"Authorization": f"Bearer {self.key}"},
            json=body,
        )
        r.raise_for_status()
        return r.json()["choices"][0]["message"]

    async def dispatch(self, name, args):
        if name in ("list_dir", "grep_search", "read_file", "write_app_map"):
            try:
                return await self.tool_map[name].ainvoke(args)
            except (ValueError, OSError, RuntimeError, TypeError, KeyError) as e:
                return f"TOOL ERROR: {e}"
        if name == "generate_macros_from_app_map":
            from app.core.atlas.source import persistence

            m = await persistence.get_app_map(int(args["app_map_id"]))
            if m is None:
                return f"app_map {args['app_map_id']} not found"
            out = await self.task_body(app_map_id=m.id, project_id=m.project_id, member_id=m.member_id)
            return json.dumps(out, ensure_ascii=False)
        return f"unknown tool {name}"

    async def run_entity(self, skill, entity, log):
        mission = f"""{skill}

---

你的任务：调研当前项目（ThinkPHP 商城后台，工作目录即项目根）的 **{entity}** 这一个实体，产出它的 AppMap 并生成宏。

约束：
- 聚焦：控制器 app/shop/controller/ 下对应文件 + 视图 app/shop/view/{entity}/（若存在）+ b2c_mall.sql 中 1~3 张主表（用 grep_search 搜 CREATE TABLE，**不要枚举所有相关表**）。
- controller/line、page/line 引用你 grep/read 看到的真实行号；element name 必须是源码中真实符号。
- 必须收录：列表页搜索框、结果表格、表单保存/提交按钮。
- 工具返回 "No matches" 或找不到时，换一个查询或放弃该条目，**绝不要重复同一个查询**。
- 流程：探索 → write_app_map（若被拒，按提示修正后重试一次）→ generate_macros_from_app_map → finish。
"""
        messages = [{"role": "user", "content": mission}]
        seen_calls: dict[str, int] = {}
        for turn in range(1, MAX_TURNS_PER_ENTITY + 1):
            msg = await self.llm(messages, tools=TOOL_SCHEMAS)
            messages.append(msg)
            tool_calls = msg.get("tool_calls") or []
            if not tool_calls:
                if msg.get("content"):
                    log(f"    [t{turn}] agent: {msg['content'][:100]}")
                continue
            for tc in tool_calls:
                name = tc["function"]["name"]
                try:
                    args = json.loads(tc["function"]["arguments"] or "{}")
                except json.JSONDecodeError:
                    args = {}
                log(f"    [t{turn}] {name}({json.dumps(args, ensure_ascii=False)[:80]})")

                if name == "finish":
                    return args.get("summary", "")

                sig = f"{name}:{json.dumps(args, sort_keys=True, ensure_ascii=False)}"
                seen_calls[sig] = seen_calls.get(sig, 0) + 1
                if seen_calls[sig] > 2:
                    result_str = "你已重复完全相同的查询多次，答案不会变化。停止重复，换一个查询或直接进行下一步。"
                else:
                    result = await self.dispatch(name, args)
                    result_str = result if isinstance(result, str) else str(result)
                    if len(result_str) > 10000:
                        result_str = result_str[:10000] + "\n... [truncated]"
                messages.append({"role": "tool", "tool_call_id": tc["id"], "content": result_str})
        return "MAX_TURNS reached"


async def main():
    from dotenv import dotenv_values
    import httpx  # noqa: F401  (used via AgentRunner globals below)

    key = dotenv_values(f"{BACKEND}/../.env").get("DASHSCOPE_API_KEY")
    assert key

    from app.infrastructure.database.resource_manager import db_resource_manager

    await db_resource_manager.initialize(create_tables=True, seed_data=False)

    from app.core.context.manager import ContextManager, EvoContext

    ctx = EvoContext(thread_id="thread-agent", project_id=PROJECT_ID, member_id=0, working_directory=MALL)
    token = ContextManager.set(ctx)

    import inspect

    from app.core.execution.macro import tasks as macro_tasks

    fn = getattr(macro_tasks.synthesize_macros_task, "func", macro_tasks.synthesize_macros_task)
    task_body = fn
    if not inspect.iscoroutinefunction(task_body):
        for cell in getattr(fn, "__closure__", None) or []:
            if inspect.iscoroutinefunction(cell.cell_contents):
                task_body = cell.cell_contents
                break

    from app.core.tools.registry import get_tool_map

    runner = AgentRunner(key, get_tool_map(), task_body)

    try:
        # ---------- Phase A: agent discovers entities ----------
        print("[A] Agent 自主发现实体...")
        listing = await runner.dispatch("list_dir", {"path": "app/shop/controller"})
        msg = await runner.llm(
            [
                {
                    "role": "user",
                    "content": (
                        "下面是一个 ThinkPHP 商城后台 app/shop/controller 目录列表。请挑出**业务实体**控制器"
                        "（对应后台有 CRUD 页面 + 数据库表的领域对象，如 Goods/Order/Member），"
                        "排除基础设施类（Base*/Login/Index/Error/Upload/Config/System/H5/Ueditor/Upgrade/Verify/Export/Account/Address/Message/Notice/Printer/Stat/Local/Album/Adv/Article*/Help/Diy/Express/Delivery/Gamesrecords/Cashorder/Siteaddress/Shopacceptmessage/Shophelp/Virtualgoods）。\n"
                        "只输出 JSON 数组，元素为小写实体名（如 [\"goods\",\"order\"]）。\n\n"
                        f"{listing}"
                    ),
                }
            ]
        )
        text = msg["content"].strip()
        entities = json.loads(text[text.find("[") : text.rfind("]") + 1])
        entities = [str(e).lower() for e in entities][:12]
        print(f"    发现 {len(entities)} 个实体: {entities}")

        # ---------- Phase B: per-entity independent agent task ----------
        skill = open(f"{BACKEND}/app/config/skills/app_map_analysis/SKILL.md", encoding="utf-8").read()
        summaries = {}
        for entity in entities:
            print(f"[B] 调研 {entity} ...")
            summaries[entity] = await runner.run_entity(skill, entity, lambda s: print(s))
    finally:
        await runner.close()
        ContextManager.reset(token)

    # ---------- final DB report ----------
    from sqlalchemy import select

    from app.infrastructure.database import session_scope
    from app.models.app_map import AppMap
    from app.models.macro import Macro

    async with session_scope() as db:
        maps = (await db.execute(select(AppMap).where(AppMap.project_id == PROJECT_ID))).scalars().all()
        macros = (await db.execute(select(Macro).where(Macro.project_id == PROJECT_ID))).scalars().all()

    print("\n" + "=" * 76)
    print(f"{'entity':<16} {'v':>3} {'actions':>8} {'elements':>9} {'macros':>7}")
    print("-" * 76)
    for m in sorted(maps, key=lambda x: x.entity or ""):
        n = len([x for x in macros if x.app_map_id == m.id])
        print(f"{m.entity:<16} {m.map_version:>3} {len(m.actions or []):>8} {len(m.elements or []):>9} {n:>7}")
    print("-" * 76)
    print(f"合计: {len(maps)} 张地图, {len(macros)} 个宏候选")
    for e, s in summaries.items():
        print(f"  {e}: {str(s)[:100]}")

    await db_resource_manager.shutdown()


import httpx  # noqa: E402

asyncio.run(main())
