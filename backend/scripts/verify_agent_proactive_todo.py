
import asyncio
import os
import sys
from langchain_core.messages import HumanMessage, AIMessage
from sqlalchemy import select

# Add project root to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.infrastructure.database.sql.database import session_scope, engine, Base
from app.infrastructure.database.sql.models.todo import TodoItem

# -------------------------------------------------------------
# UNIT TEST: finish_node logic isolation
# -------------------------------------------------------------
async def verify_proactive_unit():
    print("Ensuring DB tables exist...")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    print("Database tables ensured (Drop/Create).")

    from app.core.engine.nodes.finish import finish_node
    
    print("\n--- Testing finish_node Logic Directly ---")
    thread_id = "test-proactive-unit"
    config = {"configurable": {"thread_id": thread_id}}
    
    # Mock State with Conversation Context
    mock_messages = [
        HumanMessage(content="Start the long running deployment script."),
        AIMessage(content="Deployment started. It will take about 30 minutes. PID: 999."),
        HumanMessage(content="Okay. Remind me to check the deployment logs in 30 mins.")
    ]
    
    mock_state = {
        "messages": mock_messages,
        "project_id": 1,
        "tool_history": []
    }
    
    print("Invoking finish_node directly...")
    try:
        result = await finish_node(mock_state, config)
        print("finish_node executed.")
        
        # Check result for text output
        msgs = result.get("messages", [])
        if msgs:
            print(f"Result Message: {msgs[0].content}")
            
    except Exception as e:
        print(f"Error executing finish_node: {e}")
        import traceback
        traceback.print_exc()

    print("Checking DB for Created Todo...")
    
    async with session_scope() as session:
        # We look for a todo created recently
        stmt = select(TodoItem).order_by(TodoItem.created_at.desc()).limit(1)
        result = await session.execute(stmt)
        todo = result.scalar_one_or_none()
        
        if todo:
            print(f"✅ Found Todo Item: {todo.title}")
            print(f"   Due Date: {todo.due_date}")
            if "check" in todo.title.lower() or "deploy" in todo.title.lower():
                 print("   -> Context matched.")
            else:
                 print("   -> Context mismatch.")
        else:
             print("❌ No Todo Item found (Logic Failed).")

if __name__ == "__main__":
    asyncio.run(verify_proactive_unit())
