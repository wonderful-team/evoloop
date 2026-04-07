"""
Unit tests for Wiki Agent.

Note: These tests are designed for Embedded Mode (LocalCelery).
No external Redis/Celery infrastructure is required.
"""
import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch, Mock
import sys


# Mock heavy dependencies before importing
@pytest.fixture(autouse=True, scope="module")
def mock_dependencies():
    """Mock heavy dependencies for testing."""
    # Create mock modules
    mock_langchain = MagicMock()
    mock_langchain.messages = MagicMock()
    mock_langchain.messages.HumanMessage = MagicMock
    mock_langchain.messages.AIMessage = MagicMock
    mock_langchain.messages.BaseMessage = MagicMock
    mock_langchain.runnables = MagicMock()
    mock_langchain.runnables.RunnableConfig = MagicMock
    
    mock_langgraph = MagicMock()
    mock_langgraph.graph = MagicMock()
    mock_langgraph.graph.message = MagicMock()
    mock_langgraph.graph.message.add_messages = lambda x, y: x + y
    mock_langgraph.graph.END = "END"
    mock_langgraph.graph.StateGraph = MagicMock
    
    # Add to sys.modules
    sys.modules['langchain_core'] = mock_langchain
    sys.modules['langchain_core.messages'] = mock_langchain.messages
    sys.modules['langchain_core.runnables'] = mock_langchain.runnables
    sys.modules['langgraph'] = mock_langgraph
    sys.modules['langgraph.graph'] = mock_langgraph.graph
    sys.modules['langgraph.graph.message'] = mock_langgraph.graph.message
    
    yield
    
    # Cleanup
    for mod in list(sys.modules.keys()):
        if 'langchain' in mod or 'langgraph' in mod:
            del sys.modules[mod]


class TestWikiAgentState:
    """Test WikiAgentState structure."""

    def test_state_structure(self, mock_dependencies):
        """Verify WikiAgentState has all required fields."""
        from app.domain.wiki.agent_state import WikiAgentState
        
        # Check required keys exist in annotations
        required_keys = [
            "messages",
            "thread_id", 
            "project_id",
            "execution_ticket",
            "blackboard",
            "project_path",
            "file_tree",
            "wiki_structure",
            "pages_to_generate",
            "current_page_index",
            "generated_pages",
            "force_regenerate",
        ]
        
        annotations = WikiAgentState.__annotations__
        for key in required_keys:
            assert key in annotations, f"Missing key: {key}"


class TestWikiRouter:
    """Test Wiki Router node."""

    @pytest.mark.asyncio
    async def test_wiki_router_initialization(self, mock_dependencies):
        """Test router initializes state correctly."""
        from app.domain.wiki.nodes.router import wiki_router
        
        state = {
            "execution_ticket": {
                "parameters": {
                    "project_id": 123,
                    "force_regenerate": True,
                },
                "topic": "Test Documentation",
            }
        }
        config = MagicMock()
        
        with patch("app.domain.wiki.nodes.router.logger"):
            result = await wiki_router(state, config)
        
        assert result["project_id"] == 123
        assert result["force_regenerate"] is True
        assert result["current_page_index"] == 0
        assert result["generated_pages"] == []

    def test_route_decision_structure(self, mock_dependencies):
        """Test route decision logic."""
        from app.domain.wiki.nodes.router import route_decision
        
        # No structure -> structure phase
        state_no_structure = {"wiki_structure": None}
        assert route_decision(state_no_structure) == "structure"
        
        # Has structure but no pages -> finish
        state_empty = {"wiki_structure": [], "pages_to_generate": []}
        assert route_decision(state_empty) == "finish"
        
        # Has pages to generate -> content phase
        state_with_pages = {
            "wiki_structure": [{"id": "test"}],
            "pages_to_generate": [{"id": "test"}],
            "current_page_index": 0,
        }
        assert route_decision(state_with_pages) == "content"
        
        # All pages done -> finish
        state_done = {
            "wiki_structure": [{"id": "test"}],
            "pages_to_generate": [{"id": "test"}],
            "current_page_index": 1,
        }
        assert route_decision(state_done) == "finish"
        
        # Error state -> END
        state_error = {"error": "Something went wrong"}
        assert route_decision(state_error) == "END"


class TestStructureWorker:
    """Test Structure Worker node."""

    def test_flatten_structure(self, mock_dependencies):
        """Test structure flattening."""
        from app.domain.wiki.nodes.structure_worker import StructureWorkerNode
        
        node = StructureWorkerNode()
        
        hierarchical = [
            {
                "id": "root",
                "title": "Root",
                "description": "Root page",
                "relevant_files": [],
                "importance": "high",
                "children": [
                    {"id": "child1", "title": "Child 1", "description": "", "relevant_files": [], "importance": "medium", "children": []},
                    {"id": "child2", "title": "Child 2", "description": "", "relevant_files": [], "importance": "medium", "children": []},
                ]
            }
        ]
        
        flat = node._flatten_structure(hierarchical)
        
        assert len(flat) == 3
        assert flat[0]["id"] == "root"
        assert flat[0]["parent_id"] is None
        assert flat[1]["id"] == "child1"
        assert flat[1]["parent_id"] == "root"
        assert flat[2]["id"] == "child2"
        assert flat[2]["parent_id"] == "root"

    def test_paths_to_tree_string(self, mock_dependencies):
        """Test file tree string generation."""
        from app.domain.wiki.nodes.structure_worker import StructureWorkerNode
        
        node = StructureWorkerNode()
        paths = ["src/main.py", "src/utils.py", "tests/test_main.py"]
        
        tree = node._paths_to_tree_string(paths)
        
        assert "src" in tree
        assert "main.py" in tree
        assert "utils.py" in tree
        assert "tests" in tree

    def test_create_fallback_structure(self, mock_dependencies):
        """Test fallback structure creation."""
        from app.domain.wiki.nodes.structure_worker import StructureWorkerNode
        
        node = StructureWorkerNode()
        fallback = node._create_fallback_structure()
        
        assert len(fallback) == 3
        assert fallback[0]["id"] == "overview"
        assert fallback[1]["id"] == "architecture"
        assert fallback[2]["id"] == "setup"


class TestContentWorker:
    """Test Content Worker node."""

    def test_content_router(self, mock_dependencies):
        """Test content routing logic."""
        from app.domain.wiki.nodes.content_worker import content_router
        
        # More pages to generate
        state_more = {
            "current_page_index": 0,
            "pages_to_generate": [{"id": "1"}, {"id": "2"}],
        }
        assert content_router(state_more) == "next_page"
        
        # All done
        state_done = {
            "current_page_index": 2,
            "pages_to_generate": [{"id": "1"}, {"id": "2"}],
        }
        assert content_router(state_done) == "finish"


class TestWikiFinishNode:
    """Test Wiki Finish node."""

    @pytest.mark.asyncio
    async def test_finish_no_project_id(self, mock_dependencies):
        """Test finish handles missing project_id."""
        from app.domain.wiki.nodes.finish import wiki_finish_node
        
        state = {
            "project_id": None,
            "generated_pages": [],
        }
        config = MagicMock()
        
        result = await wiki_finish_node(state, config)
        
        assert result["error"] == "No project_id in state"
        assert result["next_node"] == "END"

    @pytest.mark.asyncio
    async def test_finish_no_pages(self, mock_dependencies):
        """Test finish handles no generated pages."""
        from app.domain.wiki.nodes.finish import wiki_finish_node
        
        state = {
            "project_id": 1,
            "generated_pages": [],
            "wiki_structure": [],
        }
        config = MagicMock()
        
        result = await wiki_finish_node(state, config)
        
        assert result["next_node"] == "END"


class TestWikiAgentEngine:
    """Test Wiki Agent Engine - Embedded Mode compatible."""

    @pytest.mark.asyncio
    async def test_initialization(self, mock_dependencies):
        """Test engine initialization."""
        from app.domain.wiki.agent_engine import WikiAgentEngine
        
        engine = WikiAgentEngine()
        assert not engine._initialized
        
        # Mock graph builder for embedded mode
        with patch("app.domain.wiki.agent_engine.GraphBuilder") as mock_builder:
            mock_graph = MagicMock()
            mock_builder.return_value.build = MagicMock(return_value=mock_graph)
            
            with patch("app.domain.wiki.agent_engine.get_checkpointer", new_callable=AsyncMock) as mock_checkpointer:
                await engine.initialize()
        
        assert engine._initialized

    @pytest.mark.asyncio
    async def test_generate_wiki(self, mock_dependencies):
        """Test wiki generation via engine."""
        from app.domain.wiki.agent_engine import WikiAgentEngine
        
        engine = WikiAgentEngine()
        engine._initialized = True
        engine.graph = MagicMock()
        engine.graph.ainvoke = AsyncMock(return_value={
            "completed_pages": 3,
            "generated_pages": [
                {"title": "Page 1", "slug": "page-1"},
                {"title": "Page 2", "slug": "page-2"},
            ],
            "messages": [],
        })
        
        result = await engine.generate_wiki(
            project_id=1,
            topic="Test",
        )
        
        assert result["status"] == "success"
        assert result["project_id"] == 1
        assert result["total_pages"] == 3
        assert "thread_id" in result

    @pytest.mark.asyncio
    async def test_get_status_running(self, mock_dependencies):
        """Test getting status of running workflow."""
        from app.domain.wiki.agent_engine import WikiAgentEngine
        
        engine = WikiAgentEngine()
        engine._initialized = True
        engine.graph = MagicMock()
        
        # Mock running state
        mock_state = MagicMock()
        mock_state.values = {
            "project_id": 1,
            "current_page_index": 2,
            "total_pages": 5,
            "completed_pages": 2,
        }
        mock_state.next = ["wiki_content_worker"]  # Still running
        engine.graph.aget_state = AsyncMock(return_value=mock_state)
        
        status = await engine.get_status("test-thread-123")
        
        assert status["status"] == "running"
        assert status["current_page"] == 2
        assert status["total_pages"] == 5
        assert status["next_node"] == "wiki_content_worker"

    @pytest.mark.asyncio
    async def test_get_status_completed(self, mock_dependencies):
        """Test getting status of completed workflow."""
        from app.domain.wiki.agent_engine import WikiAgentEngine
        
        engine = WikiAgentEngine()
        engine._initialized = True
        engine.graph = MagicMock()
        
        # Mock completed state
        mock_state = MagicMock()
        mock_state.values = {
            "project_id": 1,
            "current_page_index": 5,
            "total_pages": 5,
            "completed_pages": 5,
        }
        mock_state.next = []  # Completed
        engine.graph.aget_state = AsyncMock(return_value=mock_state)
        
        status = await engine.get_status("test-thread-123")
        
        assert status["status"] == "completed"
        assert status["next_node"] is None


class TestWikiServiceIntegration:
    """Test WikiService integration with Agent - Embedded Mode."""

    @pytest.mark.asyncio
    async def test_generate_wiki_with_agent(self, mock_dependencies):
        """Test service using Agent mode."""
        from app.domain.wiki.service import WikiService
        
        service = WikiService()
        
        with patch.object(service, "_generate_wiki_via_agent", new_callable=AsyncMock) as mock_agent:
            mock_agent.return_value = []
            
            result = await service.generate_wiki(
                project_id=1,
                topic="Test",
                use_agent=True,
            )
            
            mock_agent.assert_called_once_with(
                project_id=1,
                topic="Test",
                force_regenerate=False,
            )

    @pytest.mark.asyncio
    async def test_generate_wiki_fallback_to_direct(self, mock_dependencies):
        """Test service fallback to direct LLM when Agent fails."""
        from app.domain.wiki.service import WikiService
        
        service = WikiService()
        
        with patch.object(service, "_generate_wiki_via_agent", new_callable=AsyncMock) as mock_agent:
            mock_agent.side_effect = Exception("Agent failed")
            
            with patch.object(service, "_generate_wiki_direct", new_callable=AsyncMock) as mock_direct:
                mock_direct.return_value = []
                
                # Should fallback to direct when Agent fails
                result = await service.generate_wiki(
                    project_id=1,
                    topic="Test",
                    use_agent=True,
                )
                
                mock_agent.assert_called_once()
                mock_direct.assert_called_once()

    @pytest.mark.asyncio
    async def test_generate_wiki_direct_mode(self, mock_dependencies):
        """Test service using direct LLM mode."""
        from app.domain.wiki.service import WikiService
        
        service = WikiService()
        
        with patch.object(service, "_generate_wiki_direct", new_callable=AsyncMock) as mock_direct:
            mock_direct.return_value = []
            
            result = await service.generate_wiki(
                project_id=1,
                topic="Test",
                use_agent=False,  # Direct mode
            )
            
            mock_direct.assert_called_once()


class TestWikiAgentConfig:
    """Test Wiki Agent YAML configuration."""

    def test_config_loading(self):
        """Test YAML config is valid."""
        import yaml
        
        with open("app/config/agents/wiki_agent.yml") as f:
            config = yaml.safe_load(f)
        
        assert config["name"] == "WikiAgent"
        assert config["version"] == "1.0.0"
        assert "nodes" in config
        assert "edges" in config
        assert len(config["nodes"]) == 4
        assert len(config["edges"]) == 4
        
        # Check state schema
        assert config["state_schema"] == "app.domain.wiki.agent_state.WikiAgentState"

    def test_nodes_defined(self):
        """Test all required nodes are defined."""
        import yaml
        
        with open("app/config/agents/wiki_agent.yml") as f:
            config = yaml.safe_load(f)
        
        node_ids = [node["id"] for node in config["nodes"]]
        required_nodes = ["router", "wiki_structure_worker", "wiki_content_worker", "wiki_finish"]
        
        for node_id in required_nodes:
            assert node_id in node_ids, f"Missing node: {node_id}"

    def test_edges_defined(self):
        """Test all required edges are defined."""
        import yaml
        
        with open("app/config/agents/wiki_agent.yml") as f:
            config = yaml.safe_load(f)
        
        # Check router has conditional edge
        router_edges = [e for e in config["edges"] if e["from"] == "router"]
        assert len(router_edges) == 1
        assert router_edges[0]["type"] == "conditional"


class TestEmbeddedModeCompatibility:
    """Test Embedded Mode (LocalCelery) compatibility."""

    def test_wiki_task_is_local_task(self):
        """Verify wiki task is a LocalTask in embedded mode."""
        from app.domain.wiki.tasks import generate_wiki_task
        from app.infrastructure.queue.celery import LocalTask
        
        # Verify it's a LocalTask (embedded mode)
        assert isinstance(generate_wiki_task, LocalTask)
        assert generate_wiki_task.name == "wiki_generate"

    @pytest.mark.asyncio
    async def test_wiki_task_delay(self):
        """Test wiki task delay() in embedded mode."""
        from app.domain.wiki.tasks import generate_wiki_task
        
        # In embedded mode, delay() should return LocalAsyncResult
        with patch.object(generate_wiki_task, "run", new_callable=AsyncMock) as mock_run:
            mock_run.return_value = "Wiki generated for Project 1"
            
            # Call delay - should not block
            result = generate_wiki_task.delay(project_id=1, topic="Test")
            
            # Should have an ID
            assert hasattr(result, "id")
            assert hasattr(result, "get")
            assert hasattr(result, "ready")

    def test_no_redis_required(self):
        """Verify no Redis dependency for embedded mode tests."""
        from app.core.config import settings
        
        # Embedded mode should not require Redis
        # This test documents that our tests work without external services
        assert hasattr(settings, "EMBEDDED_MODE")
