#!/usr/bin/env python3.10
"""
LLM 真实测试：让 LLM 在大目录中找到深层文件
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

async def run_conversation(llm, tools, system_prompt, user_prompt):
    print(f"\n{'='*70}")
    print(f"[TASK] {user_prompt}")
    print('='*70)
    
    messages = [("system", system_prompt), ("human", user_prompt)]
    max_rounds = 5
    
    for round_num in range(1, max_rounds + 1):
        start = time.perf_counter()
        content, tcs = await call_llm(llm, messages, tools)
        llm_time = (time.perf_counter() - start) * 1000
        
        print(f"\n[Round {round_num}] LLM: {content[:400]!r}")
        
        if not tcs:
            print(f"❌ LLM 没有调用工具，直接回答了")
            print(f"最终回答: {content}")
            return
        
        # 执行所有工具调用
        for tc in tcs:
            args = tc.get("args", tc.get("function", {}).get("arguments", {}))
            if isinstance(args, str):
                args = json.loads(args)
            
            print(f"  [Tool] list_dir({json.dumps(args, ensure_ascii=False)})")
            
            start = time.perf_counter()
            result = await list_dir.ainvoke(args)
            tool_time = (time.perf_counter() - start) * 1000
            
            lines = result.split('\n')
            non_empty = [l for l in lines if l.strip()]
            truncated = any("more entries hidden" in l for l in lines)
            
            print(f"  → {len(non_empty)} lines, {tool_time:.1f}ms, truncated={'yes' if truncated else 'no'}")
            
            # 把结果给 LLM 看
            messages.append(("human", f"[Tool result for list_dir]\n{result[:2000]}"))
    
    print(f"\n⚠️ 达到最大轮数 {max_rounds}")

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
    
    system_prompt = (
        "You are a coding assistant. Use list_dir to explore directories. "
        "When searching for a file, explore step by step: first list the directory, "
        "then navigate into relevant subdirectories. Do not guess paths."
    )
    
    # 场景 1: 找 alipay 的配置文件
    await run_conversation(
        llm, tools, system_prompt,
        f"在 {TARGET_DIR} 项目中，alipay 支付模块的配置文件在哪里？请帮我找到它的完整路径。"
    )
    
    print("\n" + "="*70)
    print("测试完成")
    print("="*70)

if __name__ == "__main__":
    asyncio.run(main())
