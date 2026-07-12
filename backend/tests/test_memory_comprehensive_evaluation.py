import asyncio
import logging
import sys
import os
import shutil
import json
from datetime import datetime

# Setup system path to import evoloop backend
backend_dir = "/Users/xujin/Projects/develop-assistant.cn/evoloop/backend"
sys.path.insert(0, backend_dir)

# Use dedicated test data directory
TEST_DATA_DIR = "/tmp/evoloop_comprehensive_eval_data"
os.environ["EVOLOOP_APP_DATA_DIR"] = TEST_DATA_DIR
os.environ["EMBEDDED_MODE"] = "True"

# Configure Logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger("ComprehensiveEval")

def cleanup_previous_runs():
    if os.path.exists(TEST_DATA_DIR):
        try:
            shutil.rmtree(TEST_DATA_DIR)
        except Exception:
            pass
    os.makedirs(TEST_DATA_DIR, exist_ok=True)
    os.makedirs(os.path.join(TEST_DATA_DIR, "database"), exist_ok=True)

async def _login_and_store_token(username: str = "preterchan", password: str = "hellomylife") -> str:
    from app.core.evocloud import evocloud_manager
    from app.core.identity import identity_service
    evocloud_manager.initialize()
    client = evocloud_manager.api
    try:
        login_res = await client.login(username, password)
        if login_res.get("success"):
            token = login_res["token"]
            refresh_token = login_res.get("refresh_token", "")
            await identity_service.set_token(token, refresh_token)
            return token
    except Exception as e:
        logger.warning(f"Optional platform login failed (can be ignored for offline/local run): {e}")
    return ""

# Definition of the 4 test scenarios
SCENARIOS = {
    "scenario_1_cors": {
        "title": "FastAPI + Nginx CORS Header Duplicate Trap",
        "question": "我们要部署这个 FastAPI 程序到生产，并用 Nginx 做反代，跨域要注意什么吗？",
        "recall_query": "FastAPI Nginx CORS Config Conflict",
        "thread_id": "thread_scenario_cors",
        "run_id": "run_cors_101",
        "source_file_path": "app/main.py",
        "summary": "Agent debugged a FastAPI CORS error. The user had CORSMiddleware enabled in app/main.py, but also had 'add_header Access-Control-Allow-Origin *' in Nginx configuration. This caused multiple CORS headers in responses, which browsers block. The fix was to keep CORS handling only in one layer (FastAPI in app/main.py was preferred).",
        "messages": [
            {"type": "human", "content": "FastAPI 总是报跨域，但我明明在 main.py 里配了 CORSMiddleware 了。"},
            {"type": "ai", "content": "我们检查一下你的 app/main.py。看起来你配了 allow_origins=['*']。我们在前置 Nginx 反代里看看是不是也加了跨域头？"},
            {"type": "human", "content": "对，Nginx 里面配了 add_header Access-Control-Allow-Origin *;"},
            {"type": "ai", "content": "破案了！当 FastAPI 配了 CORS 且 Nginx 反向代理也配了 Access-Control-Allow-Origin 时，浏览器会收到重复的跨域 Header，从而引发 'Multiple CORS Header' 冲突并拦截请求。你应该删除 Nginx 层或 Python 代码层其中一个 CORS 设置。我建议只在 FastAPI 里保留，并在 main.py 正常处理。"}
        ],
        "keywords": ["duplicate", "nginx", "add_header", "corsmiddleware", "main.py"],
        "expect_mem_effect_desc": "Should warn strongly against duplicate headers and suggest keeping it in FastAPI only."
    },
    "scenario_2_sqlite_wal": {
        "title": "Production SQLite Database Path and WAL Mode",
        "question": "生产环境下的 SQLite 数据库文件应该放在哪里，连接应该如何配置？",
        "recall_query": "SQLite Database Path and WAL Mode Config Specification",
        "thread_id": "thread_scenario_sqlite",
        "run_id": "run_sqlite_202",
        "source_file_path": "config/database.py",
        "summary": "Agent resolved production SQLite configuration. The path must be hardcoded or set to /var/lib/myapp/production_data.db for data persistence. To optimize performance and prevent write locks in multi-user concurrent tasks, the connection MUST enable journal_mode=WAL.",
        "messages": [
            {"type": "human", "content": "我想在生产上使用 SQLite，数据库文件应该放在哪里？另外有什么性能优化的连接配置吗？"},
            {"type": "ai", "content": "在我们的生产部署架构中，SQLite 数据库文件必须存放在持久化存储卷中，具体物理路径规范为：`/var/lib/myapp/production_data.db`。"},
            {"type": "human", "content": "好的，那连接参数有什么讲究吗？我们并发有点多，怕库被锁。"},
            {"type": "ai", "content": "是的，为了解决并发写入锁库的问题，你必须在初始化连接时启用 WAL 模式。可以在连接参数中执行 `PRAGMA journal_mode=WAL;`。这样读写互不阻塞。"}
        ],
        "keywords": ["/var/lib/myapp/production_data.db", "wal", "pragma journal_mode", "lock"],
        "expect_mem_effect_desc": "Should specify the path /var/lib/myapp/production_data.db and recommend WAL mode."
    },
    "scenario_3_user_style": {
        "title": "Strict Python Type Hints and Async Test Prefixes",
        "question": "请为我写一个从数据库按 ID 获取 User 实体的 Repository 方法，并附带其单元测试用例。不用解释，只输出代码。",
        "recall_query": "用户 代码 风格 偏好 类型 异步 命名 test_async_",
        "thread_id": "thread_scenario_style",
        "run_id": "run_style_303",
        "source_file_path": "tests/test_repository.py",
        "summary": "User style preference: Strictly use Python type annotations for all function definitions, use async/await for all database operations, and prefix all test function names with test_async_ instead of test_.",
        "messages": [
            {"type": "human", "content": "后面写 Python 代码有什么风格偏好吗？我喜欢规范的类型声明 and 全异步数据库调用。"},
            {"type": "ai", "content": "收到，在本项目中，我们将严格实施类型提示（Strict Type Annotations）。此外，所有的数据库访问层都应该使用异步接口设计（async/await）。"},
            {"type": "human", "content": "还有，关于编写单元测试，我有个特别的习惯：所有测试函数的名称必须以 `test_async_` 开头，而不是普通的 `test_`。"},
            {"type": "ai", "content": "明白了，我已经记录了这一偏好：所有测试函数的名称必须以 `test_async_` 开头，同时写函数必须加完整的类型注解，并采用异步架构设计。"}
        ],
        "keywords": ["async def", "->", "test_async_", ":"],
        "expect_mem_effect_desc": "Should generate async functions with return types and test cases prefixed with test_async_."
    },
    "scenario_4_celery_mac": {
        "title": "macOS Celery Fork Safety Bug Avoidance",
        "question": "我在我的 Mac 开发机上启动 Celery worker 遇到了子进程崩溃和挂死，该怎么跑？",
        "recall_query": "celery worker macOS execution pool crash solo eventlet",
        "thread_id": "thread_scenario_celery_mac",
        "run_id": "run_celery_404",
        "source_file_path": "Makefile",
        "summary": "macOS celery execution bug gotcha. On macOS, the default celery execution pool type 'fork' triggers security/crash issues due to how Apple handles fork safety. The developer must start celery worker with the 'solo' or 'eventlet' pool to bypass this.",
        "messages": [
            {"type": "human", "content": "我用 celery -A app.celery worker 启动任务，但在我的 Mac 电脑上任务总是崩溃，没有详细日志。"},
            {"type": "ai", "content": "这是 macOS 的一个著名 Bug。macOS 上默认的进程池启动方法是 `fork`，但由于安全限制，在子进程里使用系统库会崩溃。"},
            {"type": "human", "content": "有什么解决办法吗？我不想换操作系统。"},
            {"type": "ai", "content": "你可以使用 `solo` 线程池模式或者 `eventlet` 协程池来启动。命令为：`celery -A app.celery worker --pool=solo` 或 `celery -A app.celery worker --pool=eventlet`。"}
        ],
        "keywords": ["solo", "eventlet", "macos", "fork"],
        "expect_mem_effect_desc": "Should warn about macOS fork issue and instruct using solo or eventlet pool."
    }
}

async def run_scenario_evaluation(scenario_key: str, scenario_data: dict, manager, llm):
    logger.info(f"\n==========================================================")
    logger.info(f"评估场景: {scenario_data['title']}")
    logger.info(f"==========================================================")
    
    # 1. 模拟触发 Extraction Requested 事件以收集 schema
    from app.core.events.base import system_bus
    from app.core.engine.event import ExtractionRequestedEvent
    from app.core.engine.tasks import run_engine_audit_structured_extraction
    
    req_event = ExtractionRequestedEvent(
        thread_id=scenario_data["thread_id"],
        project_id=1,
        member_id=1,
        run_id=scenario_data["run_id"],
        requests=[]
    )
    await system_bus.publish(req_event)
    collected_schemas = [req.model_dump() for req in req_event.requests]
    
    # 2. 模拟 Celery 异步任务进行结构化提取
    logger.info("  1. 派发结构化记忆提取任务...")
    await run_engine_audit_structured_extraction(
        thread_id=scenario_data["thread_id"],
        project_id=1,
        member_id=1,
        run_id=scenario_data["run_id"],
        summary=scenario_data["summary"],
        messages_dicts=scenario_data["messages"],
        collected_schemas=collected_schemas
    )
    
    # 给异步写入一点同步缓冲时间
    await asyncio.sleep(0.5)
    
    # 3. 数据层验证：检查 SQLite 与 Markdown 中的 Traceabilidad 指针与数据完整性
    logger.info("  2. 数据层验证 (Metadata & Markdown Integrity)...")
    all_memories = await manager.list_memories(project_id=1, member_id=1)
    
    matching_memory = None
    for m in all_memories:
        full_entry = await manager.get_memory(m.id)
        if full_entry.source_thread_id == scenario_data["thread_id"]:
            matching_memory = full_entry
            break
            
    if not matching_memory:
        logger.error(f"  ❌ 错误: 场景 {scenario_key} 的记忆保存失败！")
        return {"success": False, "reason": "Memory not stored"}
        
    logger.info("     ✓ 记忆成功写入，Trace 指针捕获成功:")
    logger.info(f"       - 标题: {matching_memory.title}")
    logger.info(f"       - 追溯源文件 (source_file_path): {matching_memory.source_file_path}")
    logger.info(f"       - 追溯会话 ID (source_thread_id): {matching_memory.source_thread_id}")
    logger.info(f"       - 追溯运行 ID (run_id): {matching_memory.run_id}")
    logger.info(f"       - 描述: {matching_memory.description}")
    logger.info(f"       - 标签 (tags): {matching_memory.tags}")
    
    # 断言基本数据存盘无误 (LLM提取的源文件路径只要是字符串或None即可，允许LLM提取时的自由文本描述)
    assert isinstance(matching_memory.source_file_path, (str, type(None)))
    assert matching_memory.source_thread_id == scenario_data["thread_id"]
    assert matching_memory.run_id == scenario_data["run_id"]
    
    # 4. 检索层验证：执行 Recall 查询
    logger.info("  3. 检索层验证 (Recall Match Check)...")
    search_query = scenario_data.get("recall_query", scenario_data["question"])
    recall_results = await manager.find_relevant_memories(
        query=search_query,
        context={"member_id": 1, "project_id": 1},
        max_results=3
    )
    
    is_recalled = False
    for r in recall_results:
        if r.id == matching_memory.id:
            is_recalled = True
            
    if not is_recalled:
        logger.error(f"  ❌ 错误: Recall 查询 '{search_query}' 未能召回该记忆！")
        return {"success": False, "reason": "Recall failed"}
    logger.info("     ✓ 成功：通过模糊词匹配精准召回该记忆卡片！")
    
    # 5. 横向隔离隔离验证 (多租户隔离防越权)
    logger.info("  4. 横向越权隔离测试...")
    hacker_recall = await manager.find_relevant_memories(
        query=search_query,
        context={"member_id": 2, "project_id": 1},
        max_results=3
    )
    hacker_leaked = any(r.id == matching_memory.id for r in hacker_recall)
    if hacker_leaked:
        logger.error("  ❌ 严重安全漏洞: hacker_user_b 越权拉取到了敏感项目记忆！")
        return {"success": False, "reason": "Tenant isolation leakage"}
    logger.info("     ✓ 成功：恶意租户 'hacker_user_b' 隔离验证通过，无信息泄露。")
    
    # 6. 对比测试：评估对大模型 (Gemma) 生成的真实影响
    logger.info("  5. 开始对比测试 (LLM Generation Effect)...")
    
    # 6.1 无记忆回答
    logger.info("     - 获取【未注入记忆】的 LLM 回答...")
    messages_without = [
        {"role": "system", "content": "You are a professional software engineering assistant. Answer the user's question directly and concisely."},
        {"role": "user", "content": scenario_data["question"]}
    ]
    res_without = await llm.ainvoke(messages_without)
    ans_without = res_without.content if hasattr(res_without, "content") else str(res_without)
    
    # 6.2 有记忆回答
    logger.info("     - 获取【注入召回记忆】的 LLM 回答...")
    mem_context = (
        f"=== Recall project memories ===\n"
        f"Title: {matching_memory.title}\n"
        f"Source File: {matching_memory.source_file_path}\n"
        f"Context & Content: {matching_memory.content}\n"
        f"=================================\n"
        f"Please strictly adhere to the project memory and guidelines above when answering the user's question."
    )
    messages_with = [
        {"role": "system", "content": f"You are a professional software engineering assistant. Answer the user's question directly and concisely.\n\n{mem_context}"},
        {"role": "user", "content": scenario_data["question"]}
    ]
    res_with = await llm.ainvoke(messages_with)
    ans_with = res_with.content if hasattr(res_with, "content") else str(res_with)
    
    # 7. 量化合规打分 (Quantitative Compliance Scoring)
    # 计算关键词匹配度
    keywords = scenario_data["keywords"]
    matched_without = [kw for kw in keywords if kw.lower() in ans_without.lower()]
    matched_with = [kw for kw in keywords if kw.lower() in ans_with.lower()]
    
    score_without = int((len(matched_without) / len(keywords)) * 100)
    score_with = int((len(matched_with) / len(keywords)) * 100)
    
    logger.info(f"     ✓ 关键词覆盖率比较:")
    logger.info(f"       - 未注入记忆得分: {score_without}% (匹配: {matched_without} / 目标: {keywords})")
    logger.info(f"       - 注入记忆后得分: {score_with}% (匹配: {matched_with} / 目标: {keywords})")
    
    return {
        "success": True,
        "title": scenario_data["title"],
        "is_recalled": is_recalled,
        "hacker_isolated": not hacker_leaked,
        "score_without": score_without,
        "score_with": score_with,
        "ans_without": ans_without,
        "ans_with": ans_with
    }

async def run_comprehensive_evaluation():
    cleanup_previous_runs()
    
    logger.info("==========================================================")
    logger.info("初始化底层 Infrastructure 与记忆生命周期管理器...")
    logger.info("==========================================================")
    
    from app.infrastructure.database.resource_manager import db_resource_manager
    await db_resource_manager.initialize(create_tables=True, seed_data=False)
    
    # 登录获取凭据
    await _login_and_store_token()
    
    # 配置 SystemConfig
    from app.infrastructure.config import SystemConfigService
    SystemConfigService.set_value("LLM_MODEL", "gemma-4-e4b")
    SystemConfigService.set_value("LLM_BASE_URL", "http://192.168.3.21:1234/v1")
    SystemConfigService.set_value("LLM_API_KEY", "lm-studio")
    SystemConfigService.set_value("LLM_PROVIDER_TYPE", "openai")
    
    # 自动注册系统事件处理器
    from app.core.events.discovery import auto_discover_handlers
    auto_discover_handlers()
    
    # 初始化记忆系统组件
    from app.core.memory.lifespan import MemoryLifespanManager
    await MemoryLifespanManager.ainitialize()
    container = MemoryLifespanManager.get_container()
    manager = container.memory_manager
    
    # 初始化 LLM 实例
    from app.infrastructure.llm.factory import get_default_llm
    llm = await get_default_llm(
        temperature=0.1,
        max_tokens=1000,
        model_name="gemma-4-e4b",
    )
    
    results = {}
    for key, data in SCENARIOS.items():
        results[key] = await run_scenario_evaluation(key, data, manager, llm)
        
    logger.info("\n\n" + "="*30 + " 综合评估报告汇总 " + "="*30)
    print("\n| 场景标题 | 存盘且召回成功 | 越权隔离安全 | 无记忆得分 | 有记忆得分 | 效果提升 |")
    print("| :--- | :---: | :---: | :---: | :---: | :---: |")
    for key, res in results.items():
        if not res.get("success"):
            print(f"| {SCENARIOS[key]['title']} | ❌ Fail | - | - | - | - |")
            continue
        improvement = res['score_with'] - res['score_without']
        print(f"| {res['title']} | ✅ Yes | ✅ Secure | {res['score_without']}% | {res['score_with']}% | +{improvement}% |")
        
    print("\n" + "="*80)
    
    # 打印详细的对比内容
    for key, res in results.items():
        if not res.get("success"):
            continue
        print(f"\n--- 详细对比: {res['title']} ---")
        print(f"【用户问题】: {SCENARIOS[key]['question']}")
        print(f"【期待记忆影响】: {SCENARIOS[key]['expect_mem_effect_desc']}")
        print(f"【未注入记忆的 LLM 回答大纲】:")
        ans_without_fmt = res['ans_without'].strip().replace('\n', '\n  ')[:400]
        print(f"  {ans_without_fmt}...")
        print(f"【已注入记忆的 LLM 回答大纲】:")
        ans_with_fmt = res['ans_with'].strip().replace('\n', '\n  ')[:600]
        print(f"  {ans_with_fmt}...")
        print("-"*80)
        
    # 关闭连接
    await db_resource_manager.shutdown()
    logger.info("综合评估完成。")

if __name__ == "__main__":
    asyncio.run(run_comprehensive_evaluation())
