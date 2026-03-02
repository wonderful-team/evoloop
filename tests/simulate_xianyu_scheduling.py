import asyncio
import os
import sys
import json
from datetime import datetime

# Add evoloop backend to path
sys.path.append("/Users/huangjinhuan/项目/develop-assistant.cn/evoloop/backend")

async def simulate_xianyu_scheduling():
    from app.core.tools.mcp.client import mcp_client_manager
    from app.infrastructure.database.sql.database import session_scope
    
    SERVER_NAME = "crawler"
    TARGET_CRON = "0 12 * * *"
    TARGET_URL = "https://www.goofish.com/"
    TASK_NAME = "闲鱼每日采集任务"
    
    print(f"--- 步骤 1: 确保连接到 MCP 服务器 '{SERVER_NAME}' ---")
    if not await mcp_client_manager.ensure_connected(SERVER_NAME):
        print(f"错误: 无法连接到 {SERVER_NAME}。请确保后端已启动且 Crawler 配置正确。")
        return

    session = mcp_client_manager.sessions[SERVER_NAME]
    
    print(f"\n--- 步骤 2: 查询现有关于 '闲鱼' 的定时任务 ---")
    result = await session.call_tool("list_scheduled_tasks", arguments={})
    print(f"DEBUG: Raw result content: {result.content}")
    
    # Check if content is empty or unexpected
    if not result.content:
        print("错误: 任务列表返回空内容")
        return
        
    text_content = result.content[0].text
    print(f"DEBUG: Text content: {text_content}")
    
    try:
        tasks_data = json.loads(text_content)
    except Exception as e:
        print(f"JSON 解析失败: {e}")
        # 如果不是 JSON，尝试直接从 result.content[0] 获取数据（取决于 MCP 实现）
        # 有时 mcp 会序列化为字符串，有时如果是内部调用可能不同
        return
    existing_task = None
    for task in tasks_data.get("tasks", []):
        if "闲鱼" in task["name"] or "goofish" in task["url"]:
            existing_task = task
            break
            
    # 模拟 Agent 生成的“经过验证”的抓取代码
    verified_js_code = """
    // 闲鱼最新商品提取脚本 (模拟已验证版本)
    const items = [];
    const elements = document.querySelectorAll('.item-card, [class*="itemCard"]');
    elements.forEach(el => {
        const title = el.querySelector('.title, [class*="title"]')?.innerText;
        const price = el.querySelector('.price, [class*="price"]')?.innerText;
        if (title) items.push({ title, price });
    });
    return { count: items.length, top_items: items.slice(0, 5) };
    """
    
    execution_scripts = [
        {
            "type": "javascript",
            "code": verified_js_code,
            "description": "提取前5个商品的标题和价格"
        }
    ]

    if existing_task:
        print(f"发现已有任务: ID={existing_task['id']}, Name='{existing_task['name']}', Cron='{existing_task['cron_expr']}'")
        
        if existing_task["cron_expr"] != TARGET_CRON:
            print(f"检测到时间不一致。正在将 Cron 从 '{existing_task['cron_expr']}' 修改为 '{TARGET_CRON}'...")
            update_result = await session.call_tool("update_scheduled_task", arguments={
                "task_id": existing_task["id"],
                "cron_expr": TARGET_CRON,
                "execution_scripts": execution_scripts
            })
            print(f"修改结果: {update_result.content[0].text}")
        else:
            print("Cron 时间一致，无需修改。")
    else:
        print(f"未找到相关任务，正在创建新任务: '{TASK_NAME}'...")
        
        # 在创建前， Agent 通常会先跑一次模拟验证（步骤 2b）
        print("模拟步骤: 正在通过 web_crawl 验证抓取代码有效性...")
        # 注意: 这里使用 direct 模式快速验证
        # (演示目的，实际 Agent 会检查返回结果)
        
        create_result = await session.call_tool("create_scheduled_task", arguments={
            "name": TASK_NAME,
            "cron_expr": TARGET_CRON,
            "url": TARGET_URL,
            "execution_scripts": execution_scripts
        })
        print(f"创建结果: {create_result.content[0].text}")

    print("\n--- 最终状态检查 ---")
    final_list = await session.call_tool("list_scheduled_tasks", arguments={})
    print(final_list.content[0].text)

if __name__ == "__main__":
    asyncio.run(simulate_xianyu_scheduling())
