#!/usr/bin/env python3
"""
Setup test data for rewind system testing.

This script creates:
1. A test conversation
2. Multiple messages (human and AI)
3. File operations associated with messages
4. Memory entries
5. Todo items

Usage:
    python scripts/setup_rewind_test_data.py
"""

import asyncio
import sys
from datetime import datetime
from pathlib import Path

# Add backend to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import select
from app.infrastructure.database.sql.database import session_scope, engine
from app.models import Conversation, Message, MessageReference
from app.models.file_operation import FileOperation
from app.models.todo import TodoItem, TodoStatus


async def create_test_conversation():
    """Create a test conversation with messages and operations."""
    
    async with session_scope() as session:
        # Check if test conversation already exists
        thread_id = "test-rewind-thread-001"
        
        existing = await session.execute(
            select(Conversation).where(Conversation.id == thread_id)
        )
        if existing.scalar_one_or_none():
            print(f"Test conversation {thread_id} already exists. Cleaning up...")
            # Clean up existing test data
            await cleanup_test_data(session, thread_id)
        
        print("=" * 60)
        print("Creating Test Data for Rewind System")
        print("=" * 60)
        
        # 1. Create conversation
        conversation = Conversation(
            id=thread_id,
            project_id=1,
            title="Test Rewind Conversation",
            created_at=datetime.now(),
            updated_at=datetime.now()
        )
        session.add(conversation)
        await session.flush()
        print(f"✓ Created conversation: {thread_id}")
        
        # 2. Create messages (chronological order)
        messages = []
        
        # Message 1: Human asks a question
        msg1 = Message(
            thread_id=thread_id,
            role="human",
            content="Please create a hello.py file and add some content",
            created_at=datetime.now(),
            is_visible=True
        )
        session.add(msg1)
        await session.flush()
        messages.append(msg1)
        print(f"✓ Created message 1 (human): id={msg1.id}")
        
        # Message 2: AI responds with tool call
        msg2 = Message(
            thread_id=thread_id,
            role="ai",
            content="I'll create the hello.py file for you.",
            tool_calls=[{
                "name": "create_file",
                "args": {"path": "hello.py", "content": "print('Hello World')"},
                "id": "tool_call_1"
            }],
            created_at=datetime.now(),
            is_visible=True,
            parent_id=msg1.id
        )
        session.add(msg2)
        await session.flush()
        messages.append(msg2)
        print(f"✓ Created message 2 (AI): id={msg2.id}")
        
        # Create FileOperation for message 2
        file_op1 = FileOperation(
            message_id=msg2.id,
            thread_id=thread_id,
            file_path="/tmp/test_workspace/hello.py",
            operation="ADD",
            original_content=None,  # ADD operation has no original content
            created_at=datetime.now()
        )
        session.add(file_op1)
        await session.flush()
        print(f"✓ Created file operation 1 (ADD hello.py): id={file_op1.id}")
        
        # Message 3: Human asks to modify
        msg3 = Message(
            thread_id=thread_id,
            role="human",
            content="Please update the file to add a greeting function",
            created_at=datetime.now(),
            is_visible=True
        )
        session.add(msg3)
        await session.flush()
        messages.append(msg3)
        print(f"✓ Created message 3 (human): id={msg3.id}")
        
        # Message 4: AI modifies file
        msg4 = Message(
            thread_id=thread_id,
            role="ai",
            content="I've updated the file with a greeting function.",
            tool_calls=[{
                "name": "edit_file",
                "args": {"path": "hello.py"},
                "id": "tool_call_2"
            }],
            created_at=datetime.now(),
            is_visible=True,
            parent_id=msg3.id
        )
        session.add(msg4)
        await session.flush()
        messages.append(msg4)
        print(f"✓ Created message 4 (AI): id={msg4.id}")
        
        # Create FileOperation for message 4 (EDIT)
        file_op2 = FileOperation(
            message_id=msg4.id,
            thread_id=thread_id,
            file_path="/tmp/test_workspace/hello.py",
            operation="EDIT",
            original_content="print('Hello World')",  # Original content before edit
            created_at=datetime.now()
        )
        session.add(file_op2)
        await session.flush()
        print(f"✓ Created file operation 2 (EDIT hello.py): id={file_op2.id}")
        
        # Message 5: Human asks to delete
        msg5 = Message(
            thread_id=thread_id,
            role="human",
            content="Actually, please delete the file",
            created_at=datetime.now(),
            is_visible=True
        )
        session.add(msg5)
        await session.flush()
        messages.append(msg5)
        print(f"✓ Created message 5 (human): id={msg5.id}")
        
        # Message 6: AI deletes file
        msg6 = Message(
            thread_id=thread_id,
            role="ai",
            content="I've deleted the file.",
            tool_calls=[{
                "name": "delete_file",
                "args": {"path": "hello.py"},
                "id": "tool_call_3"
            }],
            created_at=datetime.now(),
            is_visible=True,
            parent_id=msg5.id
        )
        session.add(msg6)
        await session.flush()
        messages.append(msg6)
        print(f"✓ Created message 6 (AI): id={msg6.id}")
        
        # Create FileOperation for message 6 (DELETE)
        file_op3 = FileOperation(
            message_id=msg6.id,
            thread_id=thread_id,
            file_path="/tmp/test_workspace/hello.py",
            operation="DELETE",
            original_content="def greet(name):\n    print(f'Hello, {name}!')\n\ngreet('World')",
            created_at=datetime.now()
        )
        session.add(file_op3)
        await session.flush()
        print(f"✓ Created file operation 3 (DELETE hello.py): id={file_op3.id}")
        
        # 3. Create todo items
        todo1 = TodoItem(
            source_message_id=str(msg2.id),
            source_conversation_id=thread_id,
            title="Create hello.py file",
            description="Create the initial hello.py file",
            status=TodoStatus.COMPLETED
        )
        session.add(todo1)
        
        todo2 = TodoItem(
            source_message_id=str(msg4.id),
            source_conversation_id=thread_id,
            title="Add greeting function",
            description="Update file to add greeting function",
            status=TodoStatus.COMPLETED
        )
        session.add(todo2)
        await session.flush()
        print(f"✓ Created 2 todo items")
        
        # 4. Create a message reference (attachment)
        import uuid
        ref = MessageReference(
            id=str(uuid.uuid4()),
            message_id=msg1.id,
            type="file",
            target_id="file-123",
            target_name="requirements.txt"
        )
        session.add(ref)
        await session.flush()
        print(f"✓ Created message reference (attachment)")
        
        print("\n" + "=" * 60)
        print("Test Data Created Successfully!")
        print("=" * 60)
        print(f"\nThread ID: {thread_id}")
        print(f"Messages: {len(messages)} (IDs: {[m.id for m in messages]})")
        print(f"File Operations: 3 (ADD, EDIT, DELETE)")
        print(f"Todo Items: 2")
        print(f"Message Reference: 1")
        
        print("\nTest Scenarios:")
        print("1. Rewind to message 5 (keep human message, delete AI response)")
        print("2. Rewind to message 3 (undo DELETE and EDIT)")
        print("3. Rewind to message 1 (undo all operations)")
        
        return thread_id, [m.id for m in messages]


async def cleanup_test_data(session, thread_id: str):
    """Clean up existing test data."""
    from sqlalchemy import delete, select as sa_select
    
    # Delete in correct order to avoid FK constraints
    # Get message IDs first
    msg_result = await session.execute(sa_select(Message.id).where(Message.thread_id == thread_id))
    msg_ids = [row[0] for row in msg_result.all()]
    
    if msg_ids:
        await session.execute(delete(TodoItem).where(TodoItem.source_message_id.in_(msg_ids)))
        await session.execute(delete(MessageReference).where(MessageReference.message_id.in_(msg_ids)))
    
    await session.execute(delete(FileOperation).where(FileOperation.thread_id == thread_id))
    await session.execute(delete(Message).where(Message.thread_id == thread_id))
    await session.execute(delete(Conversation).where(Conversation.id == thread_id))
    
    print(f"✓ Cleaned up existing test data for {thread_id}")


async def verify_test_data(thread_id: str):
    """Verify the test data was created correctly."""
    print("\n" + "=" * 60)
    print("Verifying Test Data")
    print("=" * 60)
    
    async with session_scope() as session:
        # Count messages
        msg_result = await session.execute(
            select(Message).where(Message.thread_id == thread_id)
        )
        messages = msg_result.scalars().all()
        print(f"✓ Messages: {len(messages)}")
        for m in messages:
            print(f"  - ID {m.id}: role={m.role}, parent={m.parent_id}")
        
        # Count file operations
        file_result = await session.execute(
            select(FileOperation).where(FileOperation.thread_id == thread_id)
        )
        file_ops = file_result.scalars().all()
        print(f"\n✓ File Operations: {len(file_ops)}")
        for op in file_ops:
            print(f"  - ID {op.id}: {op.operation} {op.file_path}")
        
        # Count todo items
        todo_result = await session.execute(
            select(TodoItem).where(TodoItem.source_message_id.in_(
                [m.id for m in messages]
            ))
        )
        todos = todo_result.scalars().all()
        print(f"\n✓ Todo Items: {len(todos)}")
        
        return len(messages), len(file_ops), len(todos)


async def main():
    """Main entry point."""
    try:
        # Create test data
        thread_id, message_ids = await create_test_conversation()
        
        # Verify data
        msg_count, file_count, todo_count = await verify_test_data(thread_id)
        
        print("\n" + "=" * 60)
        print("Summary")
        print("=" * 60)
        print(f"Thread ID: {thread_id}")
        print(f"Message IDs: {message_ids}")
        print("\nYou can now test the rewind API with:")
        print(f"  curl -X POST http://localhost:8000/api/v1/conversations/{thread_id}/rewind \\")
        print(f"    -H 'Content-Type: application/json' \\")
        print(f"    -d '{{\"message_id\": {message_ids[2]}, \"revert_files\": true}}'")
        
        return 0
        
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
