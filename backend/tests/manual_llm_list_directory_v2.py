#!/usr/bin/env python3.10
"""
LLM 真实测试 V2：验证修复后的 list_dir
"""
import asyncio
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from app.infrastructure.llm.adaptive import AdaptiveChatOpenAI
from app.domain.tools.files.list_dir import list_dir

async def call_llm(llm, messages, tools):
    response = await llm.ainvoke(messages, tools=tools, tool_choice="auto")
    return response.content, getattr(response, "tool_calls", None) or []

async def run_scenario(llm, tools, system_prompt, user_prompt, scenario_name, check_fn=None):
    print(f"\n{'='*60}")
    print(f"[SCENARIO] {scenario_name}")
    print('='*60)
    
    messages = [("system", system_prompt), ("human", user_prompt)]
    content, tcs = await call_llm(llm, messages, tools)
    
    print(f"[LLM thinking] {content[:500]!r}")
    print(f"[Tool calls] {len(tcs)}")
    
    if not tcs:
        print("❌ No tool calls")
        return None, None
    
    args = tcs[0].get("args", tcs[0].get("function", {}).get("arguments", {}))
    if isinstance(args, str):
        import json
        args = json.loads(args)
    
    print(f"[Tool call] list_dir({args})")
    
    result = await list_dir.ainvoke(args)
    print(f"\n[Tool output - first 600 chars]\n{result[:600]}")
    print(f"[Output stats] {len(result)} chars, {result.count(chr(10))} lines")
    
    if check_fn:
        check_fn(result)
    
    return args, result

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
                "filter (str, e.g. '*.py'), stats (bool, default True), with_symbols (bool)."
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
                },
                "required": ["path"],
            },
        },
    }]
    
    system_prompt = "You are a helpful coding assistant. You have access to directory exploration tools."
    test_dir = str(PROJECT_ROOT / "app" / "domain" / "tools")
    
    # Scenario 1: filter 找 .py 文件（验证目录是否被过滤）
    def check_filter(result):
        lines = [l for l in result.split('\n') if l.strip() and not l.startswith('...')]
        dirs = [l for l in lines if l.endswith('/')]
        files = [l for l in lines if not l.endswith('/')]
        print(f"\n[Check] {len(files)} files, {len(dirs)} dirs")
        if dirs:
            print(f"⚠️ Directories still present: {dirs}")
        else:
            print("✅ No directories in filter result")
        # All non-dir lines should end with .py
        non_py = [f for f in files if not f.strip().startswith('.') and '.py' not in f.split()[0]]
        if non_py:
            print(f"⚠️ Non-.py files: {non_py[:3]}")
        else:
            print("✅ All files are .py")
    
    await run_scenario(
        llm, tools, system_prompt,
        f"List ONLY the Python files in {test_dir}. Do not show directories.",
        "Filter *.py (check dirs removed)",
        check_filter
    )
    
    # Scenario 2: depth=2 探索（验证 LLM 是否加 tree=True）
    def check_depth(result):
        lines = result.split('\n')
        indented = [l for l in lines if l.startswith('  ')]
        print(f"\n[Check] {len(indented)} indented lines (depth > 1)")
        if indented:
            print("✅ tree=True + depth works (indented content found)")
        else:
            print("⚠️ No indented content - may be flat list")
    
    large_dir = str(PROJECT_ROOT / "app" / "core")
    await run_scenario(
        llm, tools, system_prompt,
        f"Show me the directory structure of {large_dir} up to 2 levels deep. I need to see nested folders.",
        "Depth=2 with tree (check nested)",
        check_depth
    )
    
    # Scenario 3: 截断测试
    def check_truncation(result):
        lines = result.split('\n')
        truncated = any("more entries hidden" in l for l in lines)
        line_count = len([l for l in lines if l.strip()])
        print(f"\n[Check] {line_count} non-empty lines, truncated={truncated}")
        if line_count <= 205:  # Allow small margin
            print("✅ Within reasonable limit")
        else:
            print(f"⚠️ {line_count} lines - may exceed limit")
    
    xlarge_dir = str(PROJECT_ROOT / "app")
    await run_scenario(
        llm, tools, system_prompt,
        f"Show me ALL files and folders in {xlarge_dir} at depth 3. Everything.",
        "Depth=3 large dir (check truncation)",
        check_truncation
    )
    
    print("\n" + "=" * 60)
    print("ALL SCENARIOS COMPLETE")
    print("=" * 60)

if __name__ == "__main__":
    asyncio.run(main())
