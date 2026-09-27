"""Regression tests for SecureVaultService encrypt/decrypt chain.

Unlike the pure crypto round-trip tests (test_secret_key_consumers.py), these
exercise the real consumer: SecureVaultService writes a credential encrypted
with SECRET_KEY-derived Fernet, and reads it back decrypted. This guards the
full "encrypt at write → decrypt at read" path that would break if SECRET_KEY
were not stable across restarts.
"""

from sqlmodel import SQLModel, create_engine

import app.models.credential  # noqa: F401  register SecureCredential with SQLModel.metadata
from app.infrastructure.config.vault import SecureVaultService
from app.infrastructure.database.resource_manager import db_resource_manager


def _make_sync_engine(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path}/vault_test.db")
    SQLModel.metadata.create_all(engine)
    return engine


def _patch_sync_engine(engine):
    db_resource_manager._sync_engine = engine
    return engine


def test_vault_write_and_read_round_trip(tmp_path):
    engine = _make_sync_engine(tmp_path)
    _patch_sync_engine(engine)
    try:
        payload = {"username": "admin", "password": "s3cr3t-pass"}
        SecureVaultService.add_credential(
            identifier="ci-ssh",
            type="ssh",
            payload=payload,
            project_id=1,
            description="test",
        )

        read_back = SecureVaultService.get_credential_payload(
            "ci-ssh", project_id=1
        )
        assert read_back == payload

        # DB row must hold ciphertext, never plaintext
        from sqlmodel import Session, select

        from app.models.credential import SecureCredential

        with Session(engine) as session:
            row = session.exec(
                select(SecureCredential).where(SecureCredential.identifier == "ci-ssh")
            ).first()
            assert row is not None
            assert row.encrypted_payload != str(payload)
    finally:
        db_resource_manager._sync_engine = None


def test_vault_update_merges_and_reencrypts(tmp_path):
    """add_credential on an existing key must decrypt old payload, merge, and
    store the merged result (covers the decrypt_payload consumer at vault.py:57)."""
    engine = _make_sync_engine(tmp_path)
    _patch_sync_engine(engine)
    try:
        SecureVaultService.add_credential(
            identifier="ci-env",
            type="env",
            payload={"host": "10.0.0.1", "port": 22},
            project_id=1,
        )
        SecureVaultService.add_credential(
            identifier="ci-env",
            type="env",
            payload={"host": "10.0.0.2", "new_key": "added"},
            project_id=1,
        )

        merged = SecureVaultService.get_credential_payload("ci-env", project_id=1)
        assert merged == {"host": "10.0.0.2", "port": 22, "new_key": "added"}
    finally:
        db_resource_manager._sync_engine = None


def test_vault_global_credential_readable_from_project(tmp_path):
    """Global (project_id=None) credentials must be readable in a project context."""
    engine = _make_sync_engine(tmp_path)
    _patch_sync_engine(engine)
    try:
        SecureVaultService.add_credential(
            identifier="ci-global",
            type="api_key",
            payload={"api_key": "sk-123"},
            project_id=None,
        )
        payload = SecureVaultService.get_credential_payload("ci-global", project_id=5)
        assert payload == {"api_key": "sk-123"}
    finally:
        db_resource_manager._sync_engine = None
