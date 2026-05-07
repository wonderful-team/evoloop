import os
import uuid
import json
import pytest
from fastapi.testclient import TestClient

# Mock Environment
os.environ["EMBEDDED_MODE"] = "true"

from app.main import app
from app.infrastructure.database.sql.database import session_scope
from app.models import Message, Conversation

client = TestClient(app)

def test_full_lifecycle():
    print("\n🚀 Starting Internal Full-Lifecycle Regression Test...")
    
    thread_id = str(uuid.uuid4())
    project_id = 1
    
    # 1. Start Chat (New Thread)
    print("\n[Step 1] Starting new chat...")
    resp = client.post("/api/v1/agent/chat", json={
        "message": "Hello, this is the first message.",
        "thread_id": thread_id,
        "project_id": project_id
    })
    assert resp.status_code == 200, f"Chat failed: {resp.text}"
    data = resp.json()
    first_msg_id = data["message_id"]
    print(f"   - Thread ID: {thread_id}")
    print(f"   - First Message ID: {first_msg_id}")

    # 2. Check Messages List (Conversations API)
    print("\n[Step 2] Fetching messages list...")
    resp = client.get(f"/api/v1/conversations/{thread_id}/messages")
    assert resp.status_code == 200, f"List messages failed: {resp.text}"
    data = resp.json()
    messages = data["data"]
    print(f"   - Found {len(messages)} messages")
    
    # Verify first message parent_id is None
    first_msg = next(m for m in messages if m["sequence_number"] == 1)
    assert first_msg["parent_id"] is None, f"First message should not have parent, got {first_msg['parent_id']}"
    
    # Note: In TestClient, background tasks (AI response) might not have finished.
    # But persist_user_message should be done.

    # 3. Test Message Search
    print("\n[Step 3] Testing Message Search...")
    resp = client.get("/api/v1/conversations/search", params={"q": "first message"})
    assert resp.status_code == 200
    search_results = resp.json()
    print(f"   - Search found {len(search_results)} results")
    assert any(r["thread_id"] == thread_id for r in search_results), "Search should find our message"

    # 4. Test Rewind
    print("\n[Step 4] Testing Rewind...")
    # Rewind to the first message
    resp = client.post(f"/api/v1/conversations/{thread_id}/rewind", json={
        "message_id": first_msg_id,
        "revert_files": False
    })
    assert resp.status_code == 200, f"Rewind failed: {resp.text}"
    print(f"   - Rewind status: {resp.json()['status']}")

    # 5. Test Memory
    print("\n[Step 5] Testing Memory Listing...")
    resp = client.get("/api/v1/memory/concepts", params={"project_id": project_id})
    assert resp.status_code == 200
    print(f"   - Concepts found: {len(resp.json())}")

    # 6. Delete Conversation
    print("\n[Step 6] Deleting conversation...")
    resp = client.delete(f"/api/v1/conversations/{thread_id}")
    assert resp.status_code == 200
    print("   - Conversation deleted.")

    print("\n✅ Full-Lifecycle Regression Test Passed!")

if __name__ == "__main__":
    test_full_lifecycle()
