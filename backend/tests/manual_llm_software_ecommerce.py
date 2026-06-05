#!/usr/bin/env python3.10
"""
LLM 真实测试：software-ecommerce 大目录探索
"""
import asyncio, sys, json, time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from app.infrastructure.llm.adaptive import AdaptiveChatOpenAI
from app.domain.tools.files.list_dir import list_dir

TARGET_DIR = "software-ecommerce"

async def call_llm(llm, messages, tools):
    response = await llm.ainvoke(messages, tools=tools, tool_choice="auto")
    return response.content, getattr(response, "tool_calls", None) or []

async def run_scenario(llm, tools, system_prompt, user_prompt, scenario_name):
    print(f"\n{'='*70}")
    print(f"[SCENARIO] {scenario_name}")
    print('='*70)
    
    messages = [("system", system_prompt), ("human", user_prompt)]
    
    start = time.perf_counter()
    content, tcs = await call_llm(llm, messages, tools)
    llm_time = (time.perf_counter() - start) * 1000
    
    print(f"[LLM thinking] {content[:600]!r}")
    print(f"[Tool calls] {len(tcs)}  (LLM 耗时: {llm_time:.1f}ms)")
    
    if not tcs:
        print("❌ LLM 没有调用工具")
        return None
    
    args = tcs[0].get("args", tcs[0].get("function", {}).get("arguments", {}))
    if isinstance(args, str):
        args = json.loads(args)
    
    print(f"[Tool call] list_dir({json.dumps(args, ensure_ascii=False)})")
    
    start = time.perf_counter()
    result = await list_dir.ainvoke(args)
    tool_time = (time.perf_counter() - start) * 1000
    
    lines = result.split('\n')
    non_empty = [l for l in lines if l.strip()]
    truncated = any("more entries hidden" in l for l in lines)
    
    print(f"\n[OUTPUT first 1000 chars]\n{result[:1000]}")
    if len(result) > 1000:
        print(f"\n... ({len(result) - 1000} more chars)")
    
    print(f"\n[STATS]")
    print(f"  总字符: {len(result)}")
    print(f"  总行数: {len(lines)}")
    print(f"  非空行: {len(non_empty)}")
    print(f"  工具耗时: {tool_time:.2f}ms")
    print(f"  截断: {'⚠️ 是' if truncated else '✅ 否'}")
    
    return result

async def main():
    llm = AdaptiveChatOpenAI(
        api_key="not-needed",
        base_url="http://localhost:1234/v1",
        model="google/gemma-4-e4b",
        temperature=0.1,
    )
    
    tools = [{
        "type": "function",
        "function": {
            "name": "list_dir",
            "description": (
                "Browse and explore directory contents with filtering, stats, and tree view.\n"
                "Use this to explore project structure, find files by type, and analyze directories.\n"
                "Args: path (REQUIRED), tree (bool), depth (int, default 1, ONLY works with tree=True), "
                "filter (str, e.g. '*.py'), stats (bool, default True), with_symbols (bool), "
                "max_entries (int, default 200). Increase to see more entries in large directories."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string"},
                    "tree": {"type": "boolean"},
                    "depth": {"type": "integer"},
                    "filter": {"type": "string"},
                    "stats": {"type": "boolean"},
                    "with_symbols": {"type": "boolean"},
                    "max_entries": {"type": "integer"},
                },
                "required": ["path"],
            },
        },
    }]
    
    system_prompt = "You are a helpful coding assistant. You have access to directory exploration tools."
    
    # 场景 1: 基本探索 - 看看根目录
    await run_scenario(
        llm, tools, system_prompt,
        f"请查看 {TARGET_DIR} 的根目录，告诉我里面有什么文件和文件夹。",
        "基本探索：根目录"
    )
    
    # 场景 2: 找 PHP 文件
    await run_scenario(
        llm, tools, system_prompt,
        f"在 {TARGET_DIR} 的根目录下，只列出所有的 PHP 文件。",
        "过滤：只找 PHP 文件"
    )
    
    # 场景 3: 深度探索 addon 目录
    await run_scenario(
        llm, tools, system_prompt,
        f"探索 {TARGET_DIR}/addon 目录的层级结构，我想看到它下面有哪些子目录和文件，最多看到 2 层深度。",
        "深度探索：addon 目录 (2层)"
    )
    
    # 场景 4: 深度探索 src 目录
    await run_scenario(
        llm, tools, system_prompt,
        f"看看 {TARGET_DIR}/src 目录的结构，展示所有文件和子目录。",
        "深度探索：src 目录"
    )
    
    # 场景 5: 超大目录 vendor
    await run_scenario(
        llm, tools, system_prompt,
        f"查看 {TARGET_DIR}/vendor 目录下有什么，只看第一层。",
        "超大目录：vendor (47个子目录)"
    )
    
    # 场景 6: 主动测试 max_entries — 让 LLM 调大限制看更多
    await run_scenario(
        llm, tools, system_prompt,
        f"我想完整查看 {TARGET_DIR}/addon 目录的 2 层结构，内容很多，请确保能看到全部内容，不要截断。",
        "max_entries 测试：LLM 主动调大限制"
    )
    
    print("\n" + "="*70)
    print("所有测试完成")
    print("="*70)

if __name__ == "__main__":
    asyncio.run(main())
