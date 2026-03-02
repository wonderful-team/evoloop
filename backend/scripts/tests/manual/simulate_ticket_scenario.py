
import asyncio
import os
import sys
from langchain_core.messages import HumanMessage, AIMessage, SystemMessage
from sqlalchemy import select

# Add project root to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.infrastructure.database.sql.database import session_scope, engine, Base
from app.models.todo import TodoItem

# -------------------------------------------------------------
# SCENARIO SIMULATION: Buy Train Ticket -> Browser Fail -> Proactive Todo
# -------------------------------------------------------------
async def simulate_ticket_scenario():
    print("Ensuring DB tables exist...")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    
    from app.core.engine.nodes.finish import finish_node
    
    print("\n--- Simulating Scenario: 'Help me buy a Spring Festival train ticket' ---")
    thread_id = "sim-ticket-1"
    config = {"configurable": {"thread_id": thread_id}}
    
    # Mocking the Conversation History that leads to Finish
    # 1. User asks
    # 2. Browser Agent tries and fails (mocked)
    messages = [
        HumanMessage(content="帮我买一张春节回家过年的火车票"),
        AIMessage(content="好的，我尝试访问 12306 网站进行购票。"),
        # ... internal tool calls omitted ...
        AIMessage(content="我已访问 12306.cn，但是系统要求登录和短信验证码，由于安全限制，我无法完成支付和验证。请您手动登录完成购票。")
    ]
    
    # Ideally, the agent SHOULD create a Todo here because the task is NOT done.
    
    mock_state = {
        "messages": messages,
        "project_id": 1,
        "tool_history": ["browser_navigate", "browser_click"]
    }
    
    print("Invoking finish_node with Browser Failure context...")
    try:
        result = await finish_node(mock_state, config)
        
        # Check result message
        msgs = result.get("messages", [])
        if msgs:
            print(f"\n[Agent Final Response]:\n{msgs[0].content}\n")
            
    except Exception as e:
        print(f"Error executing finish_node: {e}")

    print("Checking DB for Created Todo...")
    async with session_scope() as session:
        # Look for the ticket todo
        stmt = select(TodoItem).order_by(TodoItem.created_at.desc()).limit(1)
        result = await session.execute(stmt)
        todo = result.scalar_one_or_none()
        
        if todo:
            print(f"✅ Found Todo Item: {todo.title}")
            print(f"   Description: {todo.description}")
            if "票" in todo.title or "ticket" in todo.title.lower():
                 print("   -> Context matched (Agent successfully caught the unfinished task!).")
            else:
                 print("   -> Context mismatch.")
        else:
             print("❌ No Todo Item found. (Agent missed the unfinished task)")

if __name__ == "__main__":
    asyncio.run(simulate_ticket_scenario())
