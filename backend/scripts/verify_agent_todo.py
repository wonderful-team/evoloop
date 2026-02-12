
import asyncio
import os
import sys

# Add project root to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.core.globals import get_graph, set_graph
from app.core.engine.graph_builder import GraphBuilder
from langchain_core.messages import HumanMessage
from app.infrastructure.database.sql.database import session_scope
from app.models.todo import TodoItem, TodoStatus
from sqlalchemy import select
from langgraph.checkpoint.memory import MemorySaver

async def verify_agent_todo():
    print("Initializing Graph...")
    # Initialize graph manually since we are not running via main.py startup
    builder = GraphBuilder()
    # Assume we are running from backend root or scripts dir
    config_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "../app/core/engine/config/agent_main.yaml"))
    
    # Use MemorySaver for in-memory testing
    checkpointer = MemorySaver()
    
    graph = builder.build(config_path, checkpointer=checkpointer)
    set_graph(graph)
    print("Graph initialized.")
    
    # Scene 1: Relative time
    print("\n--- Testing Scenario 1: Relative Time ---")
    question = "Remind me to check the deployment logs in 2 hours."
    print(f"User: {question}")
    
    thread_id = "test-agent-todo-1"
    config = {"configurable": {"thread_id": thread_id}}
    
    # We invoke the graph with the message
    # The graph usually takes a dict with "messages"
    inputs = {"messages": [HumanMessage(content=question)]}
    
    print(" invoking Agent...")
    # Using ainvoke to run the graph
    # Note: Depending on graph config, this might run tool execution loop.
    # We hope it executes manage_todo.
    
    async for event in graph.astream(inputs, config=config):
        # We can print events to see what's happening
        # print(event)
        pass
        
    print("Agent interaction complete.")
    
    # Verify DB
    async with session_scope() as session:
        # Check for latest todo
        stmt = select(TodoItem).order_by(TodoItem.created_at.desc()).limit(1)
        result = await session.execute(stmt)
        todo = result.scalar_one_or_none()
        
        if todo:
            print(f"✅ Found Todo Item: {todo.title}")
            print(f"   Due Date: {todo.due_date}")
            print(f"   Category: {todo.category}")
            print(f"   Source Msg ID: {todo.source_message_id}")
            
            # Simple assertions
            if "deployment" in todo.title.lower() or "check" in todo.title.lower():
                 print("   -> Title matches intent.")
            else:
                 print("   -> WARNING: Title might not match intent completely.")
            
            if todo.due_date:
                print("   -> Due date set.")
            else:
                print("   -> WARNING: Due date missing.")
        else:
             print("❌ No Todo Item found in DB!")

    # Scene 2: Complex extraction
    print("\n--- Testing Scenario 2: Explicit details ---")
    question2 = "Add a high priority todo to 'Review PR' for the 'Work' category."
    print(f"User: {question2}")
    
    inputs2 = {"messages": [HumanMessage(content=question2)]}
    async for event in graph.astream(inputs2, config=config):
        pass
        
    async with session_scope() as session:
        stmt = select(TodoItem).where(TodoItem.title.ilike("%Review PR%"))
        result = await session.execute(stmt)
        todo = result.scalar_one_or_none()
         
        if todo:
            print(f"✅ Found Todo Item: {todo.title}")
            print(f"   Priority: {todo.priority}")
            print(f"   Category: {todo.category}")
            
            if todo.priority.value == 'high':
                 print("   -> Priority verified.")
            if todo.category and todo.category.lower() == 'work':
                 print("   -> Category verified.")
        else:
             print("❌ Todo not found.")

if __name__ == "__main__":
    asyncio.run(verify_agent_todo())
