"""
R08-R10: Atlas SQL 存储 CRUD 回归测试

验证 SQLAtlasStore 的完整 CRUD 操作：
R08: save_app_model - 创建和更新应用模型
R09: get_app_summary / get_state_detail / get_transitions_summary / list_apps
R10: clear_all_data - 清空所有 Atlas 数据
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest


@pytest.fixture
def mock_session():
    session = AsyncMock()
    session.add = MagicMock()
    session.flush = AsyncMock()
    session.commit = AsyncMock()
    session.delete = AsyncMock()
    result_mock = MagicMock()
    result_mock.scalars.return_value.first = MagicMock(return_value=None)
    result_mock.scalars.return_value.all = MagicMock(return_value=[])
    session.execute.return_value = result_mock
    return session


@pytest.fixture
def mock_session_scope(mock_session):
    with patch("app.core.atlas.adapters.sql_store.session_scope") as ms:
        ctx = MagicMock()
        ctx.__aenter__ = AsyncMock(return_value=mock_session)
        ctx.__aexit__ = AsyncMock()
        ms.return_value = ctx
        yield ms, mock_session


@pytest.fixture
def store():
    from app.core.atlas.adapters.sql_store import SQLAtlasStore
    return SQLAtlasStore()


class TestSQLAtlasStoreSave:
    """R08: 验证 save_app_model 创建和更新。"""

    def _make_app(self, bundle_id="com.test.app", app_name="TestApp"):
        from app.core.atlas.models import (
            AtlasApp,
            AtlasElement,
            AtlasState,
            AtlasTransition,
        )
        state = AtlasState(state_id="main", window_title="Main Window", elements=[
            AtlasElement(role="BUTTON", label="OK", ax_path="/ok"),
        ])
        trans = AtlasTransition(from_state="main", action=state.elements[0], to_state="settings")
        return AtlasApp(
            app_name=app_name,
            bundle_id=bundle_id,
            platform="macos",
            version_hash="abc123",
            states={"main": state},
            transitions=[trans],
        )

    async def test_save_new_app(self, store, mock_session_scope):
        """新建应用时插入 atlas_apps + atlas_states + atlas_transitions"""
        _, session = mock_session_scope
        app = self._make_app()
        await store.save_app_model(app)
        assert session.add.called
        session.commit.assert_awaited_once()

    async def test_save_existing_app_updates(self, store, mock_session_scope):
        """更新已有应用时删除旧 states/transitions 并重新插入"""
        _, session = mock_session_scope
        existing_app = MagicMock()
        existing_app.id = 1
        existing_app.states = [MagicMock()]
        session.execute.return_value.scalars.return_value.first = MagicMock(return_value=existing_app)
        app = self._make_app()
        await store.save_app_model(app)
        assert session.delete.called
        session.commit.assert_awaited_once()


class TestSQLAtlasStoreQuery:
    """R09: 验证查询方法。"""

    @pytest.fixture
    def mock_orm_app(self):
        from app.models.atlas import AtlasApp as AtlasAppModel
        app = MagicMock(spec=AtlasAppModel)
        app.id = 1
        app.app_name = "TestApp"
        app.bundle_id = "com.test.app"
        app.platform = "macos"
        app.version_hash = "abc123"
        return app

    async def test_get_app_summary(self, store, mock_session_scope, mock_orm_app):
        """get_app_summary 返回正确的摘要信息"""
        _, session = mock_session_scope
        session.execute.return_value.scalars.return_value.first = MagicMock(return_value=mock_orm_app)
        state_mock = MagicMock()
        state_mock.state_id = "main"
        state_mock.window_title = "Main Window"
        session.execute.return_value.scalars.return_value.all = MagicMock(return_value=[state_mock])

        result = await store.get_app_summary("com.test.app")
        assert result is not None
        assert result.app_name == "TestApp"
        assert result.state_count == 1

    async def test_get_app_summary_not_found(self, store, mock_session_scope):
        """应用不存在时返回 None"""
        _, session = mock_session_scope
        session.execute.return_value.scalars.return_value.first = MagicMock(return_value=None)

        result = await store.get_app_summary("com.nonexistent")
        assert result is None

    async def test_get_state_detail(self, store, mock_session_scope, mock_orm_app):
        """get_state_detail 返回状态详情（含元素）"""
        _, session = mock_session_scope
        session.execute.return_value.scalars.return_value.first = MagicMock(return_value=mock_orm_app)
        state_mock = MagicMock()
        state_mock.state_id = "main"
        state_mock.window_title = "Main Window"
        state_mock.elements_json = '[{"role": "BUTTON", "label": "OK"}]'
        session.execute.return_value.scalars.return_value.first = MagicMock(return_value=state_mock)

        result = await store.get_state_detail("com.test.app", "main")
        assert result is not None
        assert result.state_id == "main"
        assert len(result.elements) == 1

    async def test_get_transitions_summary(self, store, mock_session_scope, mock_orm_app):
        """get_transitions_summary 返回转换列表"""
        _, session = mock_session_scope
        session.execute.return_value.scalars.return_value.first = MagicMock(return_value=mock_orm_app)
        t1 = MagicMock()
        t1.from_state_id = "main"
        t1.action_label = "Click OK"
        t1.action_type = "click"
        t1.to_state_id = "settings"
        session.execute.return_value.scalars.return_value.all = MagicMock(return_value=[t1])

        result = await store.get_transitions_summary("com.test.app")
        assert len(result) == 1
        assert result[0]["from_state"] == "main"
        assert result[0]["to_state"] == "settings"

    async def test_list_apps(self, store, mock_session_scope, mock_orm_app):
        """list_apps 返回所有应用列表"""
        _, session = mock_session_scope
        session.execute.return_value.scalars.return_value.all = MagicMock(return_value=[mock_orm_app])

        result = await store.list_apps()
        assert len(result) == 1
        assert result[0].bundle_id == "com.test.app"


class TestSQLAtlasStoreClear:
    """R10: 验证 clear_all_data。"""

    async def test_clear_all_data(self, store, mock_session_scope):
        """clear_all_data 清空三个 Atlas 表"""
        _, session = mock_session_scope
        await store.clear_all_data()
        assert session.execute.call_count == 3  # delete transitions, states, apps
        session.commit.assert_awaited_once()
