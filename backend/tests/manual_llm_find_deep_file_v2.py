#!/usr/bin/env python3.10
"""
LLM 测试 v2：更聚焦的深层文件查找
"""
import asyncio, sys, json, time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from app.infrastructure.llm.adaptive import AdaptiveChatOpenAI
from app.domain.tools.files.list_dir import list_dir

async def call_llm(llm, messages, tools):
    response = await llm.ainvoke(messages, tools=tools, tool_choice="auto")
    return response.content, getattr(response, "tool_calls", None) or []

async def test_scenario(llm, tools, system_prompt, user_prompt, name):
    print(f"\n{'='*70}")
    print(f"[SCENARIO] {name}")
    print(f"[Prompt] {user_prompt}")
    print('='*70)
    
    messages = [("system", system_prompt), ("human", user_prompt)]
    start = time.perf_counter()
    content, tcs = await call_llm(llm, messages, tools)
    llm_time = (time.perf_counter() - start) * 1000
    
    print(f"[LLM] {content[:500]!r}")
    
    if not tcs:
        print("❌ 没有工具调用")
        return
    
    for tc in tcs:
        args = tc.get("args", tc.get("function", {}).get("arguments", {}))
        if isinstance(args, str):
            args = json.loads(args)
        print(f"[Tool] {json.dumps(args, ensure_ascii=False)}")
        
        result = await list_dir.ainvoke(args)
        lines = [l for l in result.split('\n') if l.strip()]
        truncated = any("more entries hidden" in l for l in result.split('\n'))
        print(f"[Result] {len(lines)} lines, truncated={'yes' if truncated else 'no'}")
        print(f"[Output first 800 chars]\n{result[:800]}")

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
                "Args: path (REQUIRED), tree (bool), depth (int, default 1, ONLY works with tree=True), "
                "filter (str), stats (bool, default True), max_entries (int, default 200). "
                "Use max_entries to increase the limit when exploring large directories."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string"},
                    "tree": {"type": "boolean"},
                    "depth": {"type": "integer"},
                    "filter": {"type": "string"},
                    "stats": {"type": "boolean"},
                    "max_entries": {"type": "integer"},
                },
                "required": ["path"],
            },
        },
    }]
    
    system_prompt = "You are a coding assistant with directory exploration tools."
    
    # 场景 1: 给定大致位置，让 LLM 深入找配置文件
    await test_scenario(
        llm, tools, system_prompt,
        "software-ecommerce/addon 目录下有个 alipay 模块，帮我看看它里面有哪些配置文件。",
        "已知位置，深入查找 alipay 配置文件"
    )
    
    # 场景 2: 模糊搜索 — 找所有 payment 相关文件
    await test_scenario(
        llm, tools, system_prompt,
        "在 software-ecommerce 项目里，哪些文件或目录和 payment / alipay 支付有关？用 tree 模式查看 addon 目录的 2 层结构。",
        "模糊搜索：找 payment 相关"
    )
    
    # 场景 3: 在大目录里找特定文件（需要调大 max_entries 或精确 filter）
    await test_scenario(
        llm, tools, system_prompt,
        "software-ecommerce/vendor 目录下有没有 symfony 相关的子目录？列出 vendor 下所有目录名（我只关心目录名，不要文件）。",
        "大目录中找特定子目录"
    )
    
    print("\n" + "="*70)
    print("测试完成")
    print("="*70)

if __name__ == "__main__":
    asyncio.run(main())
