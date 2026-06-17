import pytest
from fastapi.testclient import TestClient
from unittest.mock import MagicMock
from sqlmodel import Session

from app.main import app
from app.api.deps import get_current_user
from app.infrastructure.database.resource_manager import db_resource_manager
from app.infrastructure.config.vault import SecureVaultService

# Mock user dependency
def mock_get_current_user():
    return MagicMock(id=1, username="test_user")

@pytest.fixture(autouse=True)
def override_dependencies():
    app.dependency_overrides[get_current_user] = mock_get_current_user
    yield
    app.dependency_overrides.clear()

@pytest.fixture(autouse=True, scope="module")
async def unmock_db():
    from app.infrastructure.database.resource_manager import DatabaseResourceManager, db_resource_manager
    from app.core.config import settings
    from unittest.mock import MagicMock
    import os

    # Save settings
    orig_embedded = settings.EMBEDDED_MODE
    orig_sqlite_path = settings.SQLITE_PATH

    # Force embedded SQLite mode for isolated database testing
    settings.EMBEDDED_MODE = True
    settings.SQLITE_PATH = "test_vault.db"

    # Save original attributes or methods from class
    orig_initialize = DatabaseResourceManager.initialize
    orig_shutdown = DatabaseResourceManager.shutdown
    orig_close = DatabaseResourceManager.close
    orig_reset = DatabaseResourceManager.reset
    orig_get_raw = DatabaseResourceManager.get_raw_connection

    # Check if mocked
    init_type = type(db_resource_manager.initialize)
    mocked = "Mock" in init_type.__name__ or hasattr(db_resource_manager.initialize, "mock_calls")
    
    # Always restore original methods to ensure we use the real db logic
    # Save mocks
    mock_initialize = db_resource_manager.initialize
    mock_shutdown = db_resource_manager.shutdown
    mock_close = db_resource_manager.close
    mock_reset = db_resource_manager.reset
    mock_get_raw = db_resource_manager.get_raw_connection
    mock_initialized_val = db_resource_manager._initialized

    # Restore original methods
    db_resource_manager.initialize = orig_initialize.__get__(db_resource_manager, DatabaseResourceManager)
    db_resource_manager.shutdown = orig_shutdown.__get__(db_resource_manager, DatabaseResourceManager)
    db_resource_manager.close = orig_close.__get__(db_resource_manager, DatabaseResourceManager)
    db_resource_manager.reset = orig_reset.__get__(db_resource_manager, DatabaseResourceManager)
    db_resource_manager.get_raw_connection = orig_get_raw.__get__(db_resource_manager, DatabaseResourceManager)
    db_resource_manager._initialized = False

    yield

    # Close resources before deleting file
    try:
        await db_resource_manager.close()
    except Exception:
        pass

    # Clean up DB file
    if os.path.exists("test_vault.db"):
        try:
            os.remove("test_vault.db")
        except Exception:
            pass

    # Restore settings
    settings.EMBEDDED_MODE = orig_embedded
    settings.SQLITE_PATH = orig_sqlite_path

    if mocked:
        # Restore mocks to not affect other tests
        db_resource_manager.initialize = mock_initialize
        db_resource_manager.shutdown = mock_shutdown
        db_resource_manager.close = mock_close
        db_resource_manager.reset = mock_reset
        db_resource_manager.get_raw_connection = mock_get_raw
        db_resource_manager._initialized = mock_initialized_val

@pytest.fixture(autouse=True)
async def clean_database(unmock_db):
    await db_resource_manager.initialize()
    with Session(db_resource_manager.sync_engine) as session:
        from sqlalchemy import text
        session.execute(text("DELETE FROM secure_credentials"))
        session.commit()
    yield

client = TestClient(app)

def test_vault_api_crud():
    # 1. Verify initially empty list
    resp = client.get("/api/v1/vault/credentials")
    assert resp.status_code == 200
    assert resp.json() == []

    # 2. Add credential
    payload = {
        "identifier": "customer_test_ssh",
        "type": "ssh",
        "payload": {"host": "192.168.1.1", "password": "mypassword"},
        "project_id": 1,
        "description": "Test server credentials"
    }
    resp = client.post("/api/v1/vault/credentials", json=payload)
    assert resp.status_code == 200
    assert resp.json() == {"success": True, "identifier": "customer_test_ssh"}

    # 3. Retrieve list and verify metadata (no secrets returned)
    resp = client.get("/api/v1/vault/credentials?project_id=1")
    assert resp.status_code == 200
    credentials = resp.json()
    assert len(credentials) == 1
    assert credentials[0]["identifier"] == "customer_test_ssh"
    assert credentials[0]["type"] == "ssh"
    assert credentials[0]["description"] == "Test server credentials"
    assert "payload" not in credentials[0]
    assert "encrypted_payload" not in credentials[0]

    # Verify project isolation in list
    resp = client.get("/api/v1/vault/credentials?project_id=2")
    assert resp.status_code == 200
    assert resp.json() == []

    # 4. Delete credential
    # Deleting from wrong project context should fail
    resp = client.delete("/api/v1/vault/credentials/customer_test_ssh?project_id=2")
    assert resp.status_code == 403

    # Deleting from correct project context should succeed
    resp = client.delete("/api/v1/vault/credentials/customer_test_ssh?project_id=1")
    assert resp.status_code == 200
    assert resp.json() == {"success": True}

    # Verify database is empty again
    resp = client.get("/api/v1/vault/credentials")
    assert resp.status_code == 200
    assert resp.json() == []
