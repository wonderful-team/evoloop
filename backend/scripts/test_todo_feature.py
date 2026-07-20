import asyncio
import sys
import os

# Ensure backend path is in sys.path
sys.path.append(os.path.join(os.path.dirname(__file__), "../"))

from app.infrastructure.database.sql.database import engine, Base
from app.models.todo import TodoItem
from app.domain.tools.manage_todo import manage_todo
from app.api.routes.todos import create_todo, TodoCreate

# Import all models to ensure they are registered for create_all
from app.models import *

async def init_db():
    print("Creating tables...")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    print("Tables created.")

async def test_tool():
    print("Testing manage_todo tool...")
    
    # Test ADD
    print("\n[ACTION: ADD]")
    result = await manage_todo.ainvoke({
        "action": "add",
        "title": "Check deployment logs",
        "description": "Verify the new feature deployment",
        "due_date": "1 hour"
    })
    print(f"Result: {result}")
    
    if "Todo created" not in result:
        print("FAILED: Todo creation via tool failed.")
        return

    # Extract ID (simple parse)
    import re
    todo_id = re.search(r'ID: ([a-f0-9-]+)', result).group(1)
    
    # Test LIST
    print("\n[ACTION: LIST]")
    result_list = await manage_todo.ainvoke({
        "action": "list", 
        "status": "pending"
    })
    print(f"Result: {result_list}")
    
    if todo_id not in result_list:
        print("FAILED: Created todo not found in list.")
        return

    # Test UPDATE
    print("\n[ACTION: UPDATE]")
    result_update = await manage_todo.ainvoke({
        "action": "update",
        "todo_id": todo_id,
        "status": "completed"
    })
    print(f"Result: {result_update}")
    
    # verify update
    result_list_completed = await manage_todo.ainvoke({
        "action": "list",
        "status": "completed"
    })
    if todo_id not in result_list_completed:
         print("FAILED: Updated todo not found in completed list.")
         return

    # Test DELETE
    print("\n[ACTION: DELETE]")
    result_delete = await manage_todo.ainvoke({
        "action": "delete",
        "todo_id": todo_id
    })
    print(f"Result: {result_delete}")
    
    print("\nPassed all tool tests.")

async def main():
    await init_db()
    try:
        await test_tool()
    finally:
        await engine.dispose()

if __name__ == "__main__":
    asyncio.run(main())
