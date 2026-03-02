"""
Unit tests for Atlas Engine - Spatial Memory System.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.core.atlas.models import AtlasApp, AtlasState, AtlasElement, AtlasTransition
from app.core.atlas.engine import AtlasEngine
from app.core.atlas.ports.store import IAtlasStore


class TestAtlasModels:
    """Tests for Atlas data models."""

    def test_atlas_element_creation(self):
        """Test creating an AtlasElement."""
        element = AtlasElement(
            role="BUTTON",
            label="Save",
            ax_path="Window.SaveButton",
            bounds={"x": 100, "y": 200, "width": 80, "height": 30},
            is_enabled=True
        )

        assert element.role == "BUTTON"
        assert element.label == "Save"
        assert element.ax_path == "Window.SaveButton"
        assert element.is_enabled is True

    def test_atlas_element_to_dict(self):
        """Test AtlasElement serialization."""
        element = AtlasElement(
            role="BUTTON",
            label="Cancel",
            ax_path="Window.CancelButton"
        )

        data = element.to_dict()

        assert data["role"] == "BUTTON"
        assert data["label"] == "Cancel"
        assert data["ax_path"] == "Window.CancelButton"

    def test_atlas_element_from_dict(self):
        """Test AtlasElement deserialization."""
        data = {
            "role": "INPUT",
            "label": "Username",
            "ax_path": "Form.UsernameInput",
            "shortcut": "Cmd+U",
            "bounds": {"x": 10, "y": 20, "width": 200, "height": 30},
            "is_enabled": True,
            "parent_menu": "Edit"
        }

        element = AtlasElement.from_dict(data)

        assert element.role == "INPUT"
        assert element.label == "Username"
        assert element.shortcut == "Cmd+U"

    def test_atlas_state_creation(self):
        """Test creating an AtlasState."""
        elements = [
            AtlasElement("BUTTON", "Save", "Window.Save"),
            AtlasElement("BUTTON", "Cancel", "Window.Cancel")
        ]

        state = AtlasState(
            state_id="main_window_abc123",
            window_title="Main Window",
            elements=elements,
            screenshot_hash="hash123"
        )

        assert state.state_id == "main_window_abc123"
        assert state.window_title == "Main Window"
        assert len(state.elements) == 2
        assert state.screenshot_hash == "hash123"

    def test_atlas_state_get_element_by_label(self):
        """Test finding element by label."""
        state = AtlasState(
            state_id="test_state",
            window_title="Test",
            elements=[
                AtlasElement("BUTTON", "Submit", "Form.Submit"),
                AtlasElement("INPUT", "Email", "Form.Email")
            ]
        )

        found = state.get_element_by_label("Submit")
        assert found is not None
        assert found.role == "BUTTON"

        not_found = state.get_element_by_label("NonExistent")
        assert not_found is None

    def test_atlas_app_creation(self):
        """Test creating an AtlasApp."""
        app = AtlasApp(
            app_name="Safari",
            bundle_id="com.apple.Safari",
            platform="macos"
        )

        assert app.app_name == "Safari"
        assert app.bundle_id == "com.apple.Safari"
        assert app.platform == "macos"
        assert len(app.states) == 0

    def test_atlas_app_add_state(self):
        """Test adding state to AtlasApp."""
        app = AtlasApp(app_name="TestApp", bundle_id="com.test.app", platform="macos")

        state = AtlasState(
            state_id="state_1",
            window_title="Window 1",
            elements=[AtlasElement("BUTTON", "OK", "Win.OK")]
        )

        app.add_state(state)

        assert len(app.states) == 1
        assert "state_1" in app.states

    def test_atlas_app_add_transition(self):
        """Test adding transition to AtlasApp."""
        app = AtlasApp(app_name="TestApp", bundle_id="com.test.app", platform="macos")

        transition = AtlasTransition(
            from_state="state_1",
            action=AtlasElement("BUTTON", "Next", "Win.Next"),
            to_state="state_2",
            action_type="click"
        )

        app.add_transition(transition)

        assert len(app.transitions) == 1
        assert app.transitions[0].from_state == "state_1"

    def test_atlas_app_to_dict(self):
        """Test AtlasApp serialization."""
        app = AtlasApp(app_name="TestApp", bundle_id="com.test.app", platform="macos")
        app.add_state(AtlasState("s1", "Window 1", [AtlasElement("BUTTON", "OK", "W1.OK")]))

        data = app.to_dict()

        assert data["app_name"] == "TestApp"
        assert data["bundle_id"] == "com.test.app"
        assert "states" in data
        assert "s1" in data["states"]

    def test_atlas_app_concept_key(self):
        """Test concept key generation."""
        app = AtlasApp(app_name="Safari", bundle_id="com.apple.Safari", platform="macos")

        assert app.concept_key == "app_model:com.apple.Safari"


class TestAtlasEngine:
    """Tests for AtlasEngine."""

    @pytest.fixture
    def mock_store(self):
        """Create a mock store."""
        store = MagicMock(spec=IAtlasStore)
        store.save_app_model = AsyncMock()
        store.get_app_summary = AsyncMock()
        store.get_transitions_summary = AsyncMock()
        store.list_apps = AsyncMock()
        return store

    @pytest.fixture
    def engine(self, mock_store):
        """Create AtlasEngine with mock store."""
        return AtlasEngine(store=mock_store)

    @pytest.mark.asyncio
    async def test_on_ui_tree_observed_valid_event(self, engine, mock_store):
        """Test processing valid UI tree observation event."""
        event = MagicMock()
        event.data = {
            "bundle_id": "com.test.app",
            "window_title": "Main Window",
            "platform": "macos",
            "screenshot_hash": "hash123"
        }
        event.elements = [
            {"role": "BUTTON", "label": "Save", "ax_path": "Win.Save"},
            {"role": "BUTTON", "label": "Cancel", "ax_path": "Win.Cancel"}
        ]

        await engine.on_ui_tree_observed(event)

        mock_store.save_app_model.assert_called_once()
        call_args = mock_store.save_app_model.call_args[0][0]
        assert call_args.bundle_id == "com.test.app"
        assert len(call_args.states) == 1

    @pytest.mark.asyncio
    async def test_on_ui_tree_observed_invalid_bundle(self, engine, mock_store):
        """Test skipping event with invalid bundle_id."""
        event = MagicMock()
        event.data = {"bundle_id": "unknown", "window_title": "Test"}
        event.elements = []

        await engine.on_ui_tree_observed(event)

        mock_store.save_app_model.assert_not_called()

    @pytest.mark.asyncio
    async def test_on_ui_tree_observed_missing_bundle(self, engine, mock_store):
        """Test skipping event with missing bundle_id."""
        event = MagicMock()
        event.data = {"bundle_id": None, "window_title": "Test"}
        event.elements = []

        await engine.on_ui_tree_observed(event)

        mock_store.save_app_model.assert_not_called()

    @pytest.mark.asyncio
    async def test_query_app_atlas_single_bundle(self, engine, mock_store):
        """Test querying atlas for single bundle."""
        mock_store.get_app_summary.return_value = {
            "app_name": "TestApp",
            "state_count": 2,
            "states": [
                {"id": "state1", "title": "Window 1"},
                {"id": "state2", "title": "Window 2"}
            ]
        }
        mock_store.get_transitions_summary.return_value = [
            {"from_state": "state1", "to_state": "state2", "type": "click", "label": "Next"}
        ]

        result = await engine.query_app_atlas("com.test.app")

        assert "TestApp" in result
        assert "Window 1" in result
        assert "Window 2" in result
        assert "Known States (2)" in result

    @pytest.mark.asyncio
    async def test_query_app_atlas_multiple_bundles(self, engine, mock_store):
        """Test querying atlas for multiple bundles."""
        mock_store.get_app_summary.side_effect = [
            {"app_name": "App1", "state_count": 1, "states": [{"id": "s1", "title": "Win1"}]},
            {"app_name": "App2", "state_count": 1, "states": [{"id": "s2", "title": "Win2"}]}
        ]
        mock_store.get_transitions_summary.return_value = []

        result = await engine.query_app_atlas(["com.app1", "com.app2"])

        assert "App1" in result
        assert "App2" in result

    @pytest.mark.asyncio
    async def test_query_app_atlas_not_found(self, engine, mock_store):
        """Test querying atlas for non-existent app."""
        mock_store.get_app_summary.return_value = None

        result = await engine.query_app_atlas("com.nonexistent.app")

        assert "No atlas data found" in result

    @pytest.mark.asyncio
    async def test_list_apps_with_data(self, engine, mock_store):
        """Test listing apps when data exists."""
        mock_store.list_apps.return_value = [
            {"app_name": "Safari", "bundle_id": "com.apple.Safari", "platform": "macos"},
            {"app_name": "Xcode", "bundle_id": "com.apple.dt.Xcode", "platform": "macos"}
        ]

        result = await engine.list_apps()

        assert "Safari" in result
        assert "Xcode" in result
        assert "com.apple.Safari" in result

    @pytest.mark.asyncio
    async def test_list_apps_empty(self, engine, mock_store):
        """Test listing apps when no data exists."""
        mock_store.list_apps.return_value = []

        result = await engine.list_apps()

        assert "No applications have UI Maps" in result

    def test_generate_state_id(self, engine):
        """Test state ID generation."""
        state_id = engine._generate_state_id("com.test.app", "Main Window")

        assert state_id.startswith("mainwindow_")
        assert len(state_id) >= 18  # Should have hash suffix (format: {title}_{8-char-hash})

    def test_generate_state_id_consistency(self, engine):
        """Test state ID generation is consistent for same input."""
        state_id1 = engine._generate_state_id("com.test.app", "Window")
        state_id2 = engine._generate_state_id("com.test.app", "Window")

        assert state_id1 == state_id2


class TestAtlasTools:
    """Tests for Atlas tools integration."""

    @pytest.mark.asyncio
    async def test_query_app_atlas_tool(self):
        """Test query_app_atlas tool function."""
        from app.domain.tools.atlas import query_app_atlas

        with patch('app.domain.tools.atlas.atlas_engine') as mock_engine:
            mock_engine.query_app_atlas = AsyncMock(return_value="Atlas data for Safari")

            # Use ainvoke for evoloop_tool decorated function
            result = await query_app_atlas.ainvoke({"bundle_ids": "com.apple.Safari"})

            assert "Atlas data for Safari" in result

    @pytest.mark.asyncio
    async def test_query_app_atlas_tool_list_input(self):
        """Test query_app_atlas tool with list input."""
        from app.domain.tools.atlas import query_app_atlas

        with patch('app.domain.tools.atlas.atlas_engine') as mock_engine:
            mock_engine.query_app_atlas = AsyncMock(return_value="Atlas data")

            result = await query_app_atlas.ainvoke({"bundle_ids": ["com.app1", "com.app2"]})

            assert "Atlas data" in result

    @pytest.mark.asyncio
    async def test_query_app_atlas_tool_error(self):
        """Test query_app_atlas tool error handling."""
        from app.domain.tools.atlas import query_app_atlas

        with patch('app.domain.tools.atlas.atlas_engine') as mock_engine:
            mock_engine.query_app_atlas = AsyncMock(side_effect=Exception("DB Error"))

            result = await query_app_atlas.ainvoke({"bundle_ids": "com.test.app"})

            assert "Error:" in result
            assert "DB Error" in result

    @pytest.mark.asyncio
    async def test_list_app_atlas_tool(self):
        """Test list_app_atlas tool function."""
        from app.domain.tools.atlas import list_app_atlas

        with patch('app.domain.tools.atlas.atlas_engine') as mock_engine:
            mock_engine.list_apps = AsyncMock(return_value="App list")

            result = await list_app_atlas.ainvoke({})

            assert result == "App list"

    @pytest.mark.asyncio
    async def test_list_app_atlas_tool_error(self):
        """Test list_app_atlas tool error handling."""
        from app.domain.tools.atlas import list_app_atlas

        with patch('app.domain.tools.atlas.atlas_engine') as mock_engine:
            mock_engine.list_apps = AsyncMock(side_effect=Exception("Connection failed"))

            result = await list_app_atlas.ainvoke({})

            assert "Error:" in result
            assert "Connection failed" in result
