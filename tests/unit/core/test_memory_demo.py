#!/usr/bin/env python3
"""
Memory Search Functionality Demo
================================

Demonstrates the key improvements to memory search:
1. Multi-keyword OR search
2. Keyword extraction strategy
3. Tool documentation

Usage:
    python test_memory_demo.py
"""


def demo_multi_keyword_parsing():
    """Demonstrate multi-keyword OR search parsing."""
    print("=" * 60)
    print("Demo 1: Multi-Keyword OR Search Parsing")
    print("=" * 60)
    
    queries = [
        "PostgreSQL",
        "Docker PostgreSQL API",
        "  数据库   Docker  ",
        "错误处理 exception handling",
    ]
    
    for query in queries:
        keywords = [k.strip() for k in query.split() if k.strip()]
        
        if len(keywords) == 1:
            sql = f"content ILIKE '%{keywords[0]}%'"
        else:
            conditions = [f"content ILIKE '%{k}%'" for k in keywords]
            sql = " OR ".join(conditions)
        
        print(f"\nQuery: '{query}'")
        print(f"Keywords: {keywords}")
        print(f"SQL: {sql}")


def demo_keyword_extraction_strategy():
    """Demonstrate keyword extraction strategy."""
    print("\n" + "=" * 60)
    print("Demo 2: Keyword Extraction Strategy")
    print("=" * 60)
    
    examples = [
        {
            "user_says": "回到第3轮的方案",
            "bad_search": "第3轮方案",
            "good_search": "PostgreSQL 数据库 Docker",
            "reason": "Messages don't contain '第3轮', extract technical terms instead"
        },
        {
            "user_says": "之前说的错误处理",
            "bad_search": "之前说的",
            "good_search": "错误处理 exception handling",
            "reason": "Vague references won't match, use technical terms"
        },
        {
            "user_says": "参照刚才的API设计",
            "bad_search": "刚才",
            "good_search": "API设计 接口 REST",
            "reason": "Extract actual subject matter, not temporal markers"
        },
    ]
    
    for ex in examples:
        print(f"\nUser says: \"{ex['user_says']}\"")
        print(f"  ❌ BAD:  search_history(key=\"{ex['bad_search']}\")")
        print(f"  ✅ GOOD: search_history(key=\"{ex['good_search']}\")")
        print(f"  Why: {ex['reason']}")


def demo_context_flow():
    """Demonstrate Supervisor -> Worker context passing."""
    print("\n" + "=" * 60)
    print("Demo 3: Supervisor -> Worker Context Flow")
    print("=" * 60)
    
    print("""
User: "回到第3轮的方案"

┌──────────────────────────────────────────────────────────────┐
│  SUPERVISOR                                                  │
│  1. search_history(key="PostgreSQL 数据库 Docker")           │
│  2. Found: "Using PostgreSQL with Docker compose..."         │
│  3. route_to(                                                │
│       target="worker",                                       │
│       context={                                              │
│         "historical_context": "Previous discussion chose     │
│             PostgreSQL with Docker for database layer",      │
│         "referenced_tech": ["PostgreSQL", "Docker"]          │
│       },                                                     │
│       authorized_tools=["write_file", ...]                   │
│     )                                                        │
└──────────────────────────────────────────────────────────────┘
                            │
                            ▼
┌──────────────────────────────────────────────────────────────┐
│  WORKER                                                      │
│  Receives in Mission Ticket:                                 │
│    historical_context: "Previous discussion chose..."        │
│                                                            │
│  Worker immediately understands the background              │
│  → No need to search again                                  │
│  → Can proceed directly to implementation                   │
└──────────────────────────────────────────────────────────────┘
""")


def verify_implementation():
    """Verify the implementation files contain correct code."""
    print("\n" + "=" * 60)
    print("Demo 4: Implementation Verification")
    print("=" * 60)
    
    checks = []
    
    # Check sql_short_term.py
    with open("/Users/huangjinhuan/项目/develop-assistant.cn/evoloop/backend/app/core/memory/backends/sql_short_term.py") as f:
        content = f.read()
        checks.append((
            "sql_short_term.py has multi-keyword logic",
            "or_(*conditions)" in content and "keywords = [k.strip()" in content
        ))
    
    # Check facades.py
    with open("/Users/huangjinhuan/项目/develop-assistant.cn/evoloop/backend/app/domain/tools/facades.py") as f:
        content = f.read()
        checks.append((
            "facades.py delegates to search_chat_history",
            "await search_chat_history.ainvoke" in content
        ))
        checks.append((
            "facades.py has usage examples",
            "Examples:" in content and "之前说的" in content
        ))
    
    # Check memory_search.py
    with open("/Users/huangjinhuan/项目/develop-assistant.cn/evoloop/backend/app/domain/tools/memory_search.py") as f:
        content = f.read()
        checks.append((
            "memory_search.py has keyword strategy",
            "KEYWORD" in content and "Examples:" in content
        ))
    
    # Check supervisor prompt
    with open("/Users/huangjinhuan/项目/develop-assistant.cn/evoloop/backend/app/core/engine/prompts/templates/supervisor.prompt.j2") as f:
        content = f.read()
        checks.append((
            "supervisor.prompt.j2 has Context Recovery",
            "Context Recovery" in content and "PASS CONTEXT TO WORKER" in content
        ))
    
    # Check worker prompt
    with open("/Users/huangjinhuan/项目/develop-assistant.cn/evoloop/backend/app/core/engine/prompts/templates/worker.prompt.j2") as f:
        content = f.read()
        checks.append((
            "worker.prompt.j2 has manage_memory docs",
            "When to use `manage_memory`" in content and "KEYWORD EXTRACTION" in content
        ))
    
    for name, passed in checks:
        status = "✅ PASS" if passed else "❌ FAIL"
        print(f"  {status}: {name}")
    
    all_passed = all(p for _, p in checks)
    print(f"\n  {'✅ All checks passed!' if all_passed else '❌ Some checks failed!'}")
    return all_passed


if __name__ == "__main__":
    demo_multi_keyword_parsing()
    demo_keyword_extraction_strategy()
    demo_context_flow()
    success = verify_implementation()
    
    print("\n" + "=" * 60)
    print("Summary")
    print("=" * 60)
    print("""
Key Improvements:
1. ✅ Multi-keyword OR search: "Docker PostgreSQL" finds messages with EITHER term
2. ✅ Keyword extraction strategy: LLM extracts technical terms, not vague references
3. ✅ Complete documentation: Supervisor and Worker prompts both have usage guidance
4. ✅ Context passing: Supervisor passes search results to Worker via route_to context

Files Modified:
- backend/app/core/memory/backends/sql_short_term.py (OR search logic)
- backend/app/domain/tools/facades.py (manage_memory docstring)
- backend/app/domain/tools/memory_search.py (search_chat_history docstring)
- backend/app/core/engine/prompts/templates/supervisor.prompt.j2 (Context Recovery)
- backend/app/core/engine/prompts/templates/worker.prompt.j2 (manage_memory usage)
""")
    
    exit(0 if success else 1)
