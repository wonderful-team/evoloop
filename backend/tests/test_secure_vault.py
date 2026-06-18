import pytest
import importlib
from sqlmodel import Session

from app.core.engine.hooks import hook_system, HookEvent, HookContext, ToolInput, ToolResult
from app.infrastructure.database.resource_manager import db_resource_manager
from app.models.credential import SecureCredential
from app.utils.crypto import encrypt_payload, decrypt_payload
from app.infrastructure.config.vault import SecureVaultService

# We must ensure the security hooks are loaded and re-registered
from app.core.engine.hooks import security

@pytest.fixture(autouse=True)
def setup_security_hooks():
    """Explicitly reload security hooks for testing because conftest.py clears them."""
    importlib.reload(security)

@pytest.fixture(autouse=True, scope="module")
async def unmock_db():
    from app.infrastructure.database.resource_manager import DatabaseResourceManager, db_resource_manager
    from app.core.config import settings
    from unittest.mock import MagicMock
    import os

    print(f"\n[unmock_db] Initial settings: EMBEDDED={settings.EMBEDDED_MODE}, SQLITE_PATH={settings.SQLITE_PATH}")
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
    print(f"[unmock_db] db_resource_manager.initialize type: {init_type}, mocked detected: {mocked}")
    
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
    print(f"[unmock_db] Restored original methods and set _initialized=False")

    yield

    print("[unmock_db] Tearing down unmock_db...")
    # Close resources before deleting file
    try:
        await db_resource_manager.close()
    except Exception as e:
        print(f"[unmock_db] Error during close: {e}")

    # Clean up DB file
    if os.path.exists("test_vault.db"):
        try:
            os.remove("test_vault.db")
            print("[unmock_db] test_vault.db deleted")
        except Exception as e:
            print(f"[unmock_db] Error deleting test_vault.db: {e}")

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
        print("[unmock_db] Re-applied mocks")

@pytest.fixture(autouse=True)
async def clean_database(unmock_db):
    """Clean the secure credentials table before each test."""
    print(f"\n[clean_database] _initialized={db_resource_manager._initialized}, sync_engine={db_resource_manager.sync_engine}")
    await db_resource_manager.initialize()
    print(f"[clean_database] After initialize: _initialized={db_resource_manager._initialized}, sync_engine={db_resource_manager.sync_engine}")
    with Session(db_resource_manager.sync_engine) as session:
        # Delete all secure credentials
        from sqlalchemy import text
        print(f"[clean_database] Session bind: {session.bind}")
        session.execute(text("DELETE FROM secure_credentials"))
        session.commit()
    yield

def test_encryption_decryption():
    """Verify that payload encryption and decryption works correctly."""
    plain = '{"host": "127.0.0.1", "password": "supersecretpassword"}'
    encrypted = encrypt_payload(plain)
    assert encrypted != plain
    
    decrypted = decrypt_payload(encrypted)
    assert decrypted == plain

def test_vault_service_crud():
    """Verify SecureVaultService CRUD operations and project isolation."""
    payload = {"password": "testpassword", "key": "ssh-rsa aaa"}
    
    # 1. Add credential
    cred = SecureVaultService.add_credential(
        identifier="customer_a",
        type="ssh",
        payload=payload,
        project_id=1,
        description="Customer A SSH credentials"
    )
    assert cred.identifier == "customer_a"
    assert cred.project_id == 1
    
    # 2. Retrieve credential within the same project context
    retrieved = SecureVaultService.get_credential_payload("customer_a", project_id=1)
    assert retrieved == payload

    # 3. Retrieve credential with global context (None) - should fail due to isolation
    with pytest.raises(PermissionError):
        SecureVaultService.get_credential_payload("customer_a", project_id=None)

    # 4. Retrieve credential from another project context - should fail
    with pytest.raises(PermissionError):
        SecureVaultService.get_credential_payload("customer_a", project_id=2)

    # 5. List credentials filtered by project context
    # Global/None project lists all
    list_global = SecureVaultService.list_credentials(project_id=None)
    assert len(list_global) == 1
    assert list_global[0]["identifier"] == "customer_a"

    # Project 1 lists its own + global
    list_p1 = SecureVaultService.list_credentials(project_id=1)
    assert len(list_p1) == 1

    # Project 2 lists its own + global (p1 is excluded)
    list_p2 = SecureVaultService.list_credentials(project_id=2)
    assert len(list_p2) == 0

    # 6. Delete credential
    # Delete from wrong project context - should fail
    with pytest.raises(PermissionError):
        SecureVaultService.delete_credential("customer_a", project_id=2)

    # Delete from correct project context
    success = SecureVaultService.delete_credential("customer_a", project_id=1)
    assert success is True
    assert len(SecureVaultService.list_credentials()) == 0

async def test_placeholder_replacement_hook():
    """Verify that the HookSystem successfully replaces placeholders in tool arguments."""
    # Seed a credential
    SecureVaultService.add_credential(
        identifier="customer_a",
        type="ssh",
        payload={"password": "secret_password_123"},
        project_id=1
    )

    # Context with placeholder in command
    context = HookContext(
        thread_id="test-thread-123",
        project_id=1,
        tool_name="execute_command",
        tool_input=ToolInput(
            command='sshpass -p "{{vault.customer_a.password}}" ssh user@host',
            args={"command": 'sshpass -p "{{vault.customer_a.password}}" ssh user@host'}
        ),
        blackboard=None,
    )

    # Trigger PRE_TOOL_USE
    result = await hook_system.trigger(HookEvent.PRE_TOOL_USE, context, blocking=True)
    assert result.success is True
    
    # Verify values were replaced in modified context
    modified_ctx = result.modified_context
    assert modified_ctx is not None
    assert "secret_password_123" in modified_ctx.tool_input.command
    assert "vault.customer_a.password" not in modified_ctx.tool_input.command
    assert "secret_password_123" in modified_ctx.tool_input.args["command"]
    
    # Verify raw secret was recorded in extra
    assert "secret_password_123" in modified_ctx.extra["injected_secrets"]

async def test_placeholder_replacement_wrong_project_blocked():
    """Verify that trying to use a placeholder from another project is blocked by the hook."""
    # Seed credential under Project 1
    SecureVaultService.add_credential(
        identifier="customer_a",
        type="ssh",
        payload={"password": "secret_password_123"},
        project_id=1
    )

    # Context running under Project 2
    context = HookContext(
        thread_id="test-thread-123",
        project_id=2,  # Different project
        tool_name="execute_command",
        tool_input=ToolInput(
            command='sshpass -p "{{vault.customer_a.password}}" ssh user@host'
        ),
        blackboard=None,
    )

    result = await hook_system.trigger(HookEvent.PRE_TOOL_USE, context, blocking=True)
    # Trigger should fail and block execution because the credential belongs to Project 1
    assert result.block is True
    assert "Failed to resolve secure placeholder" in result.message
    assert "Access Denied" in result.message

async def test_post_tool_use_censorship():
    """Verify that post-execution hook successfully masks raw secrets in outputs."""
    # Seed credential
    SecureVaultService.add_credential(
        identifier="customer_a",
        type="ssh",
        payload={"password": "secret_password_123"},
        project_id=1
    )

    context = HookContext(
        thread_id="test-thread-123",
        project_id=1,
        tool_name="execute_command",
        tool_input=ToolInput(
            command='echo "injected: secret_password_123"'
        ),
        tool_result=ToolResult(
            output="Output contains raw secret: secret_password_123",
            error="Error log: secret_password_123 not accepted",
            data={"secret_field": "secret_password_123", "normal_field": "value"}
        ),
        extra={"injected_secrets": ["secret_password_123"]},
        blackboard=None,
    )

    # Trigger POST_TOOL_USE
    result = await hook_system.trigger(HookEvent.POST_TOOL_USE, context, blocking=False)
    assert result.success is True
    
    # Verify outputs are censored
    modified_ctx = result.modified_context
    assert modified_ctx is not None
    assert "secret_password_123" not in modified_ctx.tool_result.output
    assert "******" in modified_ctx.tool_result.output
    
    assert "secret_password_123" not in modified_ctx.tool_result.error
    assert "******" in modified_ctx.tool_result.error
    
    assert "secret_password_123" not in modified_ctx.tool_result.data["secret_field"]
    assert "******" in modified_ctx.tool_result.data["secret_field"]
    assert modified_ctx.tool_result.data["normal_field"] == "value"
