"""Atlas 空间记忆引擎单测（in-memory store，无 LLM/DB）。

验证：on_ui_tree_observed 把观测到的 UI 树吸收进 Atlas（元素分类、状态入库），
query_app_atlas 可检索出刚吸收的应用状态。
"""

from __future__ import annotations

from typing import Any
from unittest.mock import patch

import pytest

from app.core.atlas.engine import AtlasEngine
from app.core.atlas.models import AtlasApp
from app.core.atlas.ports.store import IAtlasStore
from app.core.atlas.schemas import AtlasAppInfo, AtlasAppSummary, AtlasStateDetail

pytestmark = pytest.mark.unit


class InMemoryAtlasStore(IAtlasStore):
    """最小 in-memory store：只记录 save_app_model 调用，供断言。"""

    def __init__(self) -> None:
        self.saved_apps: list[AtlasApp] = []

    async def save_app_model(self, atlas_app: AtlasApp) -> None:
        self.saved_apps.append(atlas_app)

    async def get_app_summary(self, bundle_id: str, platform: str = "macos") -> AtlasAppSummary | None:
        return None

    async def get_state_detail(self, bundle_id: str, state_id: str, platform: str = "macos") -> AtlasStateDetail | None:
        return None

    async def get_transitions_summary(self, bundle_id: str, platform: str = "macos") -> list[dict[str, Any]]:
        return []

    async def list_apps(self) -> list[AtlasAppInfo]:
        return []

    async def clear_all_data(self) -> None:
        self.saved_apps = []


def _ui_event(bundle_id: str, window_title: str) -> Any:
    return type(
        "Event",
        (),
        {
            "data": {
                "bundle_id": bundle_id,
                "window_title": window_title,
                "platform": "macos",
                "screenshot_hash": "shot-1",
                "version_hash": "v1",
            },
            "elements": [
                {"role": "AXButton", "label": "Save", "ax_path": "/main/save"},
                {"role": "AXTextField", "label": "Name", "ax_path": "/main/name"},
            ],
        },
    )()


class TestAtlasEngine:
    async def test_ui_tree_absorbed_into_app_model(self) -> None:
        store = InMemoryAtlasStore()
        engine = AtlasEngine(store=store)
        with patch("app.core.atlas.engine.DynamicAppTriage.get_dynamic_apps", return_value=[]):
            await engine.on_ui_tree_observed(_ui_event("com.test.app", "Main"))

        assert len(store.saved_apps) == 1, "UI tree 应被吸收为一条 app model"
        app = store.saved_apps[0]
        assert app.bundle_id == "com.test.app"
        assert app.platform == "macos"
        assert len(app.states) == 1
        state = next(iter(app.states.values()))
        assert state.window_title == "Main"
        assert len(state.elements) == 2
        labels = {e.label for e in state.elements}
        assert labels == {"Save", "Name"}

    async def test_ui_tree_without_elements_is_ignored(self) -> None:
        store = InMemoryAtlasStore()
        engine = AtlasEngine(store=store)
        with patch("app.core.atlas.engine.DynamicAppTriage.get_dynamic_apps", return_value=[]):
            await engine.on_ui_tree_observed(
                type("Event", (), {"data": {"bundle_id": "com.x"}, "elements": []})()
            )
        assert store.saved_apps == [], "无元素的 UI tree 不应入库"
