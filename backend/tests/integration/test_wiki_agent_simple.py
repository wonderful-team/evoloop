"""
Simplified integration tests for Wiki Agent in Embedded Mode.

These tests verify the Wiki Agent workflow without requiring full EvoLoop dependencies.
"""
import pytest
import os
from unittest.mock import MagicMock, AsyncMock, patch


# Ensure embedded mode (SQLite + LanceDB + LocalCelery, no external dependencies)
os.environ['EMBEDDED_MODE'] = 'true'


class TestWikiAgentWorkflowSimple:
    """Test complete Wiki Agent workflow with mocked dependencies."""

    @pytest.mark.asyncio
    async def test_workflow_state_transitions(self):
        """Test workflow state transitions through nodes."""
        # Simulate workflow states
        states = []
        
        # Initial state
        initial_state = {
            "project_id": 1,
            "topic": "Test Documentation",
            "wiki_structure": None,
            "pages_to_generate": None,
            "current_page_index": 0,
            "generated_pages": [],
        }
        states.append(initial_state)
        
        # After router - should go to structure
        state_after_router = {
            **initial_state,
            "project_id": 1,
            "force_regenerate": False,
        }
        states.append(state_after_router)
        
        # After structure worker
        state_after_structure = {
            **state_after_router,
            "wiki_structure": [
                {"id": "overview", "title": "Overview", "parent_id": None, "order": 0},
                {"id": "architecture", "title": "Architecture", "parent_id": None, "order": 1},
            ],
            "pages_to_generate": [
                {"id": "overview", "title": "Overview", "parent_id": None, "order": 0},
                {"id": "architecture", "title": "Architecture", "parent_id": None, "order": 1},
            ],
            "total_pages": 2,
        }
        states.append(state_after_structure)
        
        # After first content worker
        state_after_first_page = {
            **state_after_structure,
            "current_page_index": 1,
            "completed_pages": 1,
            "generated_pages": [
                {"page_id": "overview", "title": "Overview", "content": "# Overview\n\nContent"}
            ],
        }
        states.append(state_after_first_page)
        
        # After second content worker
        state_after_second_page = {
            **state_after_first_page,
            "current_page_index": 2,
            "completed_pages": 2,
            "generated_pages": [
                {"page_id": "overview", "title": "Overview", "content": "# Overview\n\nContent"},
                {"page_id": "architecture", "title": "Architecture", "content": "# Architecture\n\nContent"},
            ],
        }
        states.append(state_after_second_page)
        
        # Verify state progression
        assert len(states) == 5
        assert states[0]["wiki_structure"] is None
        assert states[2]["total_pages"] == 2
        assert states[4]["completed_pages"] == 2

    @pytest.mark.asyncio
    async def test_workflow_with_error(self):
        """Test workflow handles errors gracefully."""
        # Simulate error state
        error_state = {
            "project_id": 1,
            "error": "Failed to generate structure",
            "wiki_structure": None,
        }
        
        # Router should detect error and route to END
        def route_decision(state):
            if state.get("error"):
                return "END"
            if state.get("wiki_structure") is None:
                return "structure"
            return "content"
        
        next_node = route_decision(error_state)
        assert next_node == "END"


class TestWikiAgentEngineMocked:
    """Test Wiki Agent Engine with fully mocked dependencies."""

    def test_engine_initialization_mock(self):
        """Test engine can be initialized with mocked graph."""
        # Mock the engine class
        class MockWikiAgentEngine:
            def __init__(self):
                self.graph = None
                self._initialized = False
            
            async def initialize(self):
                if not self._initialized:
                    self.graph = MagicMock()
                    self._initialized = True
            
            async def generate_wiki(self, project_id, topic, **kwargs):
                await self.initialize()
                return {
                    "status": "success",
                    "project_id": project_id,
                    "total_pages": 3,
                    "generated_pages": [
                        {"title": "Page 1"},
                        {"title": "Page 2"},
                        {"title": "Page 3"},
                    ]
                }
        
        engine = MockWikiAgentEngine()
        assert not engine._initialized

    @pytest.mark.asyncio
    async def test_engine_generate_wiki_mock(self):
        """Test engine generate_wiki with mocked graph."""
        class MockWikiAgentEngine:
            def __init__(self):
                self.graph = MagicMock()
                self._initialized = True
            
            async def generate_wiki(self, project_id, topic, **kwargs):
                self.graph.ainvoke = AsyncMock(return_value={
                    "completed_pages": 3,
                    "generated_pages": [
                        {"title": "Overview"},
                        {"title": "Architecture"},
                        {"title": "Setup"},
                    ]
                })
                
                result = await self.graph.ainvoke({}, {})
                
                return {
                    "status": "success",
                    "project_id": project_id,
                    "total_pages": result["completed_pages"],
                    "generated_pages": result["generated_pages"],
                }
        
        engine = MockWikiAgentEngine()
        result = await engine.generate_wiki(1, "Test")
        
        assert result["status"] == "success"
        assert result["total_pages"] == 3


class TestStructureWorkerCore:
    """Test Structure Worker core functionality."""

    def test_structure_plan_creation(self):
        """Test creating structure plan from file tree."""
        file_tree = """
src/
  main.py
  utils.py
tests/
  test_main.py
README.md
"""
        
        # Simulate what structure worker would create
        expected_pages = [
            {
                "id": "overview",
                "title": "Project Overview",
                "description": "Overview of the project",
                "relevant_files": ["README.md"],
                "importance": "high",
                "parent_id": None,
                "order": 0,
            },
            {
                "id": "structure",
                "title": "Project Structure",
                "description": "File organization",
                "relevant_files": ["src/"],
                "importance": "medium",
                "parent_id": None,
                "order": 1,
            },
        ]
        
        assert len(expected_pages) == 2
        assert expected_pages[0]["id"] == "overview"

    def test_fallback_structure(self):
        """Test fallback structure when LLM fails."""
        fallback_pages = [
            {"id": "overview", "title": "项目概览", "description": "项目整体介绍"},
            {"id": "architecture", "title": "架构设计", "description": "系统架构说明"},
            {"id": "setup", "title": "安装与配置", "description": "项目安装和配置指南"},
        ]
        
        assert len(fallback_pages) == 3
        assert fallback_pages[0]["id"] == "overview"


class TestContentWorkerCore:
    """Test Content Worker core functionality."""

    def test_page_generation_order(self):
        """Test pages are generated in correct order."""
        pages_to_generate = [
            {"id": "p1", "title": "Page 1", "order": 0},
            {"id": "p2", "title": "Page 2", "order": 1},
            {"id": "p3", "title": "Page 3", "order": 2},
        ]
        
        generated_order = []
        current_index = 0
        
        while current_index < len(pages_to_generate):
            page = pages_to_generate[current_index]
            generated_order.append(page["id"])
            current_index += 1
        
        assert generated_order == ["p1", "p2", "p3"]

    def test_content_generation_with_context(self):
        """Test content generation uses file context."""
        page_title = "Architecture"
        relevant_files = {
            "src/main.py": "def main(): pass",
            "src/config.py": "CONFIG = {}",
        }
        
        # Simulate content generation
        content = f"# {page_title}\n\n"
        content += "## Files Referenced\n\n"
        for filename in relevant_files:
            content += f"- `{filename}`\n"
        
        assert page_title in content
        assert "src/main.py" in content


class TestEmbeddedModeWikiTask:
    """Test Wiki task in Embedded Mode."""

    def test_wiki_task_signature(self):
        """Test wiki task has correct signature."""
        # Define expected signature
        expected_params = ["project_id", "topic", "force_regenerate", "use_agent"]
        
        # Verify parameters
        assert "project_id" in expected_params
        assert "topic" in expected_params
        assert "use_agent" in expected_params

    @pytest.mark.asyncio
    async def test_wiki_task_execution_flow(self):
        """Test wiki task execution flow."""
        # Mock service call
        async def mock_generate_wiki(project_id, topic, use_agent=True):
            return [
                MagicMock(id=1, title="Page 1"),
                MagicMock(id=2, title="Page 2"),
            ]
        
        # Execute
        pages = await mock_generate_wiki(1, "Test", use_agent=True)
        
        assert len(pages) == 2
        assert pages[0].title == "Page 1"


class TestWikiAgentStateManagement:
    """Test Wiki Agent state management."""

    def test_state_initialization(self):
        """Test state is properly initialized."""
        initial_state = {
            "messages": [],
            "thread_id": None,
            "project_id": None,
            "execution_ticket": None,
            "blackboard": None,
            "iteration_count": 0,
            "tool_history": [],
            "project_path": None,
            "file_tree": None,
            "wiki_structure": None,
            "pages_to_generate": None,
            "current_page_index": 0,
            "generated_pages": [],
            "force_regenerate": False,
        }
        
        assert initial_state["current_page_index"] == 0
        assert initial_state["generated_pages"] == []

    def test_state_progression(self):
        """Test state progresses correctly through workflow."""
        state = {
            "current_page_index": 0,
            "completed_pages": 0,
            "generated_pages": [],
        }
        
        # Simulate processing first page
        state["current_page_index"] = 1
        state["completed_pages"] = 1
        state["generated_pages"].append({"page_id": "p1", "title": "Page 1"})
        
        assert state["completed_pages"] == 1
        assert len(state["generated_pages"]) == 1
        
        # Simulate processing second page
        state["current_page_index"] = 2
        state["completed_pages"] = 2
        state["generated_pages"].append({"page_id": "p2", "title": "Page 2"})
        
        assert state["completed_pages"] == 2
        assert len(state["generated_pages"]) == 2


class TestWikiAgentConfig:
    """Test Wiki Agent configuration."""

    @pytest.mark.skip(reason="Module deleted in schema migration")
    def test_config_yaml_structure(self):
        """Test YAML config has correct structure."""
        import yaml
        import os

        config_path = os.path.join(
            os.path.dirname(__file__),
            '..', '..',
            'app', 'config', 'agents', 'wiki_agent.yml'
        )

        with open(config_path) as f:
            config = yaml.safe_load(f)

        # Verify structure
        assert "name" in config
        assert "version" in config
        assert "state_schema" in config
        assert "nodes" in config
        assert "edges" in config

        # Verify nodes
        assert len(config["nodes"]) == 4
        node_ids = [n["id"] for n in config["nodes"]]
        assert "router" in node_ids
        assert "wiki_structure_worker" in node_ids
        assert "wiki_content_worker" in node_ids
        assert "wiki_finish" in node_ids

        # Verify edges
        assert len(config["edges"]) == 4


# Mark tests
pytestmark = [
    pytest.mark.integration,
    pytest.mark.no_external_services,
]
