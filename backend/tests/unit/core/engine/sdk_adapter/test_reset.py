from __future__ import annotations

import uuid

from app.core.config import settings
from app.core.engine.sdk_adapter.reset import (
    conversation_store_path,
    reset_conversation_store,
)
from app.core.engine.sdk_adapter.session_bridge import _conversation_id


def test_conversation_store_path_matches_bridge_derivation(tmp_path) -> None:
    monkey_target = tmp_path / "sdk-conversations"
    import app.core.engine.sdk_adapter.reset as reset_mod

    original = settings.EVOLOOP_APP_DATA_DIR
    settings.EVOLOOP_APP_DATA_DIR = str(tmp_path)
    try:
        assert (
            reset_mod.conversation_store_path("sdk-reset-thread")
            == monkey_target / _conversation_id("sdk-reset-thread").hex
        )
    finally:
        settings.EVOLOOP_APP_DATA_DIR = original


def test_reset_conversation_store_removes_dir_and_is_idempotent(tmp_path) -> None:

    original = settings.EVOLOOP_APP_DATA_DIR
    settings.EVOLOOP_APP_DATA_DIR = str(tmp_path)
    try:
        store = conversation_store_path("reset-me")
        store.mkdir(parents=True)
        (store / "base_state.json").write_text("{}", encoding="utf-8")

        assert reset_conversation_store("reset-me") is True
        assert not store.exists()
        assert reset_conversation_store("reset-me") is False
    finally:
        settings.EVOLOOP_APP_DATA_DIR = original


def test_conversation_store_path_accepts_uuid_thread_ids() -> None:
    tid = str(uuid.uuid4())
    assert conversation_store_path(tid).name == uuid.UUID(tid).hex
