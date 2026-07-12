import asyncio
import logging
import sys
import os
import shutil

# 设置系统路径以导入 evoloop 后端
backend_dir = "/Users/xujin/Projects/develop-assistant.cn/evoloop/backend"
sys.path.insert(0, backend_dir)

# 使用独立的临时测试数据目录
TEST_DATA_DIR = "/tmp/evoloop_effect_test_data"
os.environ["EVOLOOP_APP_DATA_DIR"] = TEST_DATA_DIR
os.environ["EMBEDDED_MODE"] = "True"

# 配置日志输出到控制台
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger("EffectTest")

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
    login_res = await client.login(username, password)
    if not login_res.get("success"):
        raise RuntimeError(f"Login failed: {login_res}")
    token = login_res["token"]
    refresh_token = login_res.get("refresh_token", "")
    await identity_service.set_token(token, refresh_token)
    return token

async def run_effect_test():
    cleanup_previous_runs()
    
    logger.info("==========================================================")
    # 1. 初始化数据库与事件总线
    logger.info("第一步：初始化底层 Infrastructure (SQLAlchemy Base + 自动建表)")
    from app.infrastructure.database.resource_manager import db_resource_manager
    await db_resource_manager.initialize(create_tables=True, seed_data=False)
    
    # 登录获取并保存 Access Token，避免 401 Unauthorized 报错
    logger.info("登录并获取平台凭证以供大模型请求...")
    try:
        await _login_and_store_token()
    except Exception as e:
        logger.warning(f"登录服务调用失败 (如果是本地直连测试，可安全忽略该警告): {e}")
    
    # 注入测试需要的系统配置，避免大模型提取时因为没有 seed 数据而报错
    from app.infrastructure.config import SystemConfigService
    SystemConfigService.set_value("LLM_MODEL", "gemma-4-e4b")
    SystemConfigService.set_value("LLM_BASE_URL", "http://192.168.3.21:1234/v1")
    SystemConfigService.set_value("LLM_API_KEY", "lm-studio")
    SystemConfigService.set_value("LLM_PROVIDER_TYPE", "openai")
    
    # 注册事件监听器
    from app.core.events.discovery import auto_discover_handlers
    auto_discover_handlers()
    
    # 初始化记忆 Lifespan 容器
    from app.core.memory.lifespan import MemoryLifespanManager
    await MemoryLifespanManager.ainitialize()
    container = MemoryLifespanManager.get_container()
    manager = container.memory_manager
    
    logger.info("✓ 底座与记忆引擎初始化成功。")
    logger.info("==========================================================")
    
    # 2. 模拟第一阶段：开发会话与 Finish LLM 记忆提取
    logger.info("第二步：模拟 Turn 1 调试开发会话 ( FastAPICORS + Nginx Header 冲突)")
    
    # 模拟的多轮消息历史（Agent 在此过程中帮助用户修改 /app/main.py 并定位了 Nginx 反向代理层多重 Origin 头的问题）
    from langchain_core.messages import HumanMessage, AIMessage
    messages = [
        HumanMessage(content="FastAPI 总是报跨域，但我明明在 main.py 里配了 CORSMiddleware 了。"),
        AIMessage(content="我来检查一下你的 /app/main.py。看起来你配了 allow_origins=['*']。我们在前置 Nginx 反代里看看是不是也加了跨域头？"),
        HumanMessage(content="对，Nginx 里面配了 add_header Access-Control-Allow-Origin *;"),
        AIMessage(content="破案了！当 FastAPI 配了 CORS 且 Nginx 反向代理也配了 Access-Control-Allow-Origin 时，浏览器会收到重复的跨域 Header，从而引发 'Multiple CORS Header' 冲突并拦截请求。你应该删除 Nginx 层或 Python 代码层其中一个 CORS 设置。我建议只在 FastAPI 里保留，并在 main.py 正常处理。")
    ]
    
    # 转换消息为 dict
    from app.core.engine.tasks import run_engine_audit_structured_extraction
    messages_dicts = []
    for m in messages:
        m_type = "human" if isinstance(m, HumanMessage) else "ai"
        messages_dicts.append({"type": m_type, "content": m.content})
        
    session_summary = (
        "Agent debugged a FastAPI CORS error. The user had CORSMiddleware enabled in /app/main.py, "
        "but also had 'add_header Access-Control-Allow-Origin *' in Nginx configuration. "
        "This caused multiple CORS headers in responses, which browsers block. "
        "The fix was to keep CORS handling only in one layer (FastAPI in /app/main.py was preferred)."
    )
    
    # 注册提取 Schema
    from app.core.events.schemas.lifecycle import ExtractionRequest
    from app.core.events.decorators import event_subscribe
    from app.core.events import SystemEventType
    from app.core.events.base import system_bus
    
    logger.info("正在模拟触发 Finish 审计的 Extraction Requested 事件...")
    
    # Debug: Check registered handlers on system_bus
    from app.core.events import SystemEventType
    handlers = system_bus._handlers.get(SystemEventType.EXTRACTION_REQUESTED.value, [])
    logger.info(f"system_bus 上注册的 EXTRACTION_REQUESTED 处理器数量: {len(handlers)}")
    for h in handlers:
        logger.info(f" - 处理器: {h.__module__}.{h.__name__} (绑定的 self: {getattr(h, '__self__', None)})")

    # 构造请求事件并收集 schema
    from app.core.engine.event import ExtractionRequestedEvent
    req_event = ExtractionRequestedEvent(
        thread_id="thread_cors_nginx_debug",
        project_id=1,
        member_id=1,
        run_id="run_debug_999",
        requests=[]
    )
    await system_bus.publish(req_event)
    
    collected_schemas = [req.model_dump() for req in req_event.requests]
    logger.info(f"收集到 {len(collected_schemas)} 个提取 schema：")
    for cs in collected_schemas:
        logger.info(f" - Schema 名字: {cs.get('name')}")
        
    attempts = 5
    for attempt in range(1, attempts + 1):
        try:
            logger.info(f"正在派发后台 Celery 任务，模拟真实的大模型 (kimi-k2-thinking-turbo) 结构化记忆提取... (第 {attempt} 次尝试)")
            await run_engine_audit_structured_extraction(
                thread_id="thread_cors_nginx_debug",
                project_id=1,
                member_id=1,
                run_id="run_debug_999",
                summary=session_summary,
                messages_dicts=messages_dicts,
                collected_schemas=collected_schemas
            )
            logger.info("✓ 大模型结构化记忆提取成功！")
            break
        except Exception as e:
            logger.warning(f"第 {attempt} 次尝试提炼失败: {e}")
            if attempt == attempts:
                logger.error("已达到最大重试次数，提炼失败。")
                raise e
            wait_time = attempt * 12
            logger.info(f"等待 {wait_time} 秒后重试...")
            await asyncio.sleep(wait_time)
    
    # 给异步写入一点同步缓冲时间
    await asyncio.sleep(1)
    
    logger.info("==========================================================")
    # 3. 验证冷记忆的写入效果与 Trace 追溯元数据
    logger.info("第三步：验证冷记忆 Markdown 文件与 SQLite 关系表中的 Trace 指针")
    
    all_memories = await manager.list_memories(project_id=1, member_id=1)
    logger.info(f"冷记忆库中的记忆条目总数：{len(all_memories)}")
    
    if not all_memories:
        logger.error("❌ 失败：没有提取到任何记忆！")
        return
        
    extracted_memory = None
    for m in all_memories:
        # 获取完整的 MemoryEntry 实体以获取 Trace 字段
        full_entry = await manager.get_memory(m.id)
        logger.info(f"发现记忆条目：")
        logger.info(f"  - 标题: {full_entry.title}")
        logger.info(f"  - 类型: {full_entry.type.value}")
        logger.info(f"  - 简短描述: {full_entry.description}")
        logger.info(f"  - 追溯文件路径 (source_file_path): {getattr(full_entry, 'source_file_path', 'None')}")
        logger.info(f"  - 追溯会话 ID (source_thread_id): {getattr(full_entry, 'source_thread_id', 'None')}")
        logger.info(f"  - 追溯执行 ID (source_run_id): {getattr(full_entry, 'source_run_id', 'None')}")
        logger.info(f"  - 详细正文: {full_entry.content}")
        
        if "nginx" in full_entry.title.lower() or "cors" in full_entry.title.lower():
            extracted_memory = full_entry
            
    if extracted_memory:
        logger.info("✅ 成功：大模型审计正确从多轮对话中提炼出项目踩坑教训！")
        if extracted_memory.source_file_path:
            logger.info(f"✅ 成功：精准追溯到了修改源文件路径 {extracted_memory.source_file_path}")
        else:
            logger.info("ℹ️ 提示：大模型未提取出 source_file_path，但其他 Trace 指针完备。")
    else:
        logger.error("❌ 失败：未提取到符合条件的跨域/Nginx记忆条目")
        
    logger.info("==========================================================")
    
    # 4. 模拟第二阶段：在新会话中大模型主动 Recall 记忆（LLM 取）
    logger.info("第四步：模拟新开发任务会话 (thread_web_deploy) 中大模型 Recall 调取记忆")
    logger.info("用户提问：'我们要部署这个 FastAPI 程序到生产，并用 Nginx 做反代，跨域要注意什么吗？'")
    logger.info("大模型感知意图，调用工具：recall(query='FastAPI Nginx CORS')")
    
    recall_results = await manager.find_relevant_memories(
        query="FastAPI Nginx CORS",
        context={"member_id": 1, "project_id": 1},
        max_results=3
    )
    
    logger.info(f"Recall 召回到的记忆条数：{len(recall_results)}")
    for r in recall_results:
        # 格式化呈现给 Agent 的水化摘要格式（验证 Traceability 体验）
        print("\n--- 呈现给 Agent 的水化记忆卡片 ---")
        print(f"Gotcha: {r.title} (ID: {r.id})")
        print(f"  - 摘要要点: {r.description}")
        print(f"  - 追溯文件: {getattr(r, 'source_file_path', 'None')}")
        print(f"  - 追溯会话: thread_{getattr(r, 'source_thread_id', 'None')} (Run: {getattr(r, 'source_run_id', 'None')})")
        print(f"  - 详情大纲: {r.content}")
        print("-----------------------------------\n")
        
    if recall_results:
        logger.info("✅ 成功：Recall 成功根据模糊词意图精准召回冷记忆！且摘要卡片携带 Trace 追溯指针！")
    else:
        logger.error("❌ 失败：在新会话中未能 Recall 召回对应记忆")
        
    logger.info("==========================================================")
    
    # 5. 验证多租户横向越权安全隔离
    logger.info("第五步：验证多用户逻辑与物理隔离安全性")
    logger.info("模拟另一个恶意开发者 'hacker_user_b' 尝试召回当前项目的敏感跨域踩坑记忆...")
    logger.info("恶意大模型感知意图，调用工具：recall(query='CORS FastAPI')")
    
    hacker_recall_results = await manager.find_relevant_memories(
        query="CORS FastAPI",
        context={"member_id": 2, "project_id": 1},
        max_results=3
    )
    
    logger.info(f"恶意开发者召回到的记忆条数：{len(hacker_recall_results)}")
    if not hacker_recall_results:
        logger.info("✅ 成功：多租户隔离验证通过！恶意开发者 'hacker_user_b' 被安全阻断，返回空召回。")
    else:
        logger.error("❌ 失败：存在安全漏洞！恶意开发者越权拉取到了属于 developer_user_a 的项目记忆！")
        
    logger.info("==========================================================")
    
    # 6. 验证取记忆数据对大模型（LLM）回答的影响
    logger.info("第六步：评估召回记忆对大模型 (Gemma) 决策的真实防御避坑效果")
    
    question = "我们要部署这个 FastAPI 程序到生产，并用 Nginx 做反代，跨域要注意什么吗？"
    from app.infrastructure.llm.factory import get_default_llm
    llm = await get_default_llm(
        temperature=0.1,
        max_tokens=1000,
        model_name="gemma-4-e4b",
    )
    
    # 6.1 无记忆（CORS Gotcha 缺失）时大模型的回答
    logger.info("  [对比测试] 发送提问给大模型（不包含任何项目 Recall 记忆）...")
    messages_without_mem = [
        {"role": "system", "content": "You are a senior DevOps assistant. Answer the user's question concisely."},
        {"role": "user", "content": question}
    ]
    res_without = await llm.ainvoke(messages_without_mem)
    content_without = res_without.content if hasattr(res_without, "content") else str(res_without)
    
    # 6.2 包含记忆卡片时大模型的回答
    logger.info("  [对比测试] 发送提问给大模型（已注入 Recall 召回的跨域 gotcha 记忆卡片）...")
    mem_context = ""
    if recall_results:
        r = recall_results[0]
        mem_context = (
            f"=== 召回的历史项目踩坑教训与Trace traceability ===\n"
            f"标题: {r.title}\n"
            f"相关文件: {getattr(r, 'source_file_path', 'None')}\n"
            f"正文: {r.content}\n"
            f"================================================\n\n"
            f"以上是该项目的真实踩坑历史，请在回答用户问题时，务必根据这行记忆发出强力警告，并指出相关源文件。"
        )
    
    messages_with_mem = [
        {"role": "system", "content": f"You are a senior DevOps assistant. Answer the user's question concisely.\n\n{mem_context}"},
        {"role": "user", "content": question}
    ]
    res_with = await llm.ainvoke(messages_with_mem)
    content_with = res_with.content if hasattr(res_with, "content") else str(res_with)
    
    print("\n" + "="*30 + " 记忆对大模型生成影响的真实对比评估 " + "="*30)
    print(f"【用户提问】:\n  {question}\n")
    print(f"【未注入 Recall 记忆时的回答】:\n{content_without}\n")
    print(f"【注入 Recall 记忆后的回答】:\n{content_with}")
    print("="*90 + "\n")
    
    logger.info("==========================================================")
    
    # 清理数据库连接资源
    await db_resource_manager.shutdown()
    logger.info("实效验证完成。")

if __name__ == "__main__":
    asyncio.run(run_effect_test())
