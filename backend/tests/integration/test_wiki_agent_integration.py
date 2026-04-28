"""
Integration tests for Wiki Agent in Embedded Mode.

These tests verify the complete Wiki Agent workflow end-to-end.
No external services (Redis/Celery) are required - all tests run in-process.

To run:
    pytest tests/integration/test_wiki_agent_integration.py -v
"""
import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch, Mock
from typing import Any
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


@pytest.fixture
def mock_project_data():
    """Fixture for mock project data."""
    return {
        "id": 1,
        "name": "Test Project",
        "path": "/tmp/test_project",
    }


@pytest.fixture
def mock_file_tree():
    """Fixture for mock file tree structure."""
    return """
src/
  main.py
  utils.py
  config.py
tests/
  test_main.py
  test_utils.py
README.md
requirements.txt
"""


@pytest.mark.skip(reason="Module deleted in schema migration")
class TestWikiAgentWorkflow:
    """Test complete Wiki Agent workflow."""

    @pytest.mark.asyncio
    async def test_full_workflow_mocked(self, mock_dependencies, mock_project_data, mock_file_tree):
        """Test full workflow with mocked dependencies."""
        from app.domain.wiki.agent_engine import WikiAgentEngine
        from app.domain.wiki.agent_state import WikiAgentState
        
        # Create engine
        engine = WikiAgentEngine()
        
        # Mock the graph
        engine._initialized = True
        engine.graph = MagicMock()
        
        # Track state changes through the workflow
        state_changes = []
        
        async def mock_ainvoke(state: WikiAgentState, config: dict) -> dict:
            """Mock graph execution simulating workflow steps."""
            state_changes.append(dict(state))
            
            # Simulate workflow completion
            return {
                "project_id": state.get("project_id"),
                "completed_pages": 3,
                "generated_pages": [
                    {"page_id": "overview", "title": "Overview", "content": "# Overview\n\nTest content"},
                    {"page_id": "architecture", "title": "Architecture", "content": "# Architecture\n\nTest content"},
                    {"page_id": "setup", "title": "Setup", "content": "# Setup\n\nTest content"},
                ],
                "messages": [],
            }
        
        engine.graph.ainvoke = mock_ainvoke
        
        # Execute
        result = await engine.generate_wiki(
            project_id=1,
            topic="Test Documentation",
        )
        
        # Verify
        assert result["status"] == "success"
        assert result["total_pages"] == 3
        assert len(result["generated_pages"]) == 3

    @pytest.mark.asyncio
    async def test_workflow_with_error_handling(self, mock_dependencies):
        """Test workflow handles errors gracefully."""
        from app.domain.wiki.agent_engine import WikiAgentEngine
        
        engine = WikiAgentEngine()
        engine._initialized = True
        engine.graph = MagicMock()
        engine.graph.ainvoke = AsyncMock(side_effect=Exception("Graph execution failed"))
        
        result = await engine.generate_wiki(
            project_id=1,
            topic="Test",
        )
        
        assert result["status"] == "failed"
        assert "error" in result


@pytest.mark.skip(reason="Module deleted in schema migration")
class TestStructureWorkerIntegration:
    """Test Structure Worker with real file operations (mocked)."""

    @pytest.mark.asyncio
    async def test_structure_generation(self, mock_dependencies, mock_file_tree):
        """Test structure generation from file tree."""
        from app.domain.wiki.nodes.structure_worker import StructureWorkerNode
        
        node = StructureWorkerNode()
        
        # Mock LLM response
        mock_llm_response = MagicMock()
        mock_llm_response.content = '''
        {
            "title": "Test Project Wiki",
            "pages": [
                {
                    "id": "overview",
                    "title": "Project Overview",
                    "description": "General project information",
                    "relevant_files": ["README.md"],
                    "importance": "high",
                    "children": []
                },
                {
                    "id": "architecture",
                    "title": "Architecture",
                    "description": "System architecture documentation",
                    "relevant_files": ["src/main.py", "src/config.py"],
                    "importance": "high",
                    "children": []
                }
            ]
        }
        '''
        
        with patch("app.domain.wiki.nodes.structure_worker.get_default_llm", new_callable=AsyncMock) as mock_llm:
            mock_llm.return_value.ainvoke = AsyncMock(return_value=mock_llm_response)
            
            with patch("app.domain.wiki.nodes.structure_worker.evocloud_manager.get_project_by_id", new_callable=AsyncMock) as mock_cloud:
                mock_cloud.return_value = {"path": "/tmp/test_project"}
                
                with patch.object(node, "_get_file_tree", return_value=mock_file_tree):
                    with patch.object(node, "_read_file_safe", return_value="# Test Project\n\nDescription"):
                        with patch("app.domain.wiki.nodes.structure_worker.WikiBuilder") as mock_builder:
                            mock_builder_instance = MagicMock()
                            mock_builder_instance.build_structure_prompt.return_value = "prompt"
                            mock_builder_instance.build_validation_prompt.return_value = "validation_prompt"
                            mock_builder.return_value = mock_builder_instance
                            
                            state = {
                                "execution_ticket": {
                                    "parameters": {"project_id": 1}
                                }
                            }
                            config = {"configurable": {"thread_id": "test"}}
                            
                            result = await node(state, config)
                            
                            assert "wiki_structure" in result
                            assert "pages_to_generate" in result


@pytest.mark.skip(reason="Module deleted in schema migration")
class TestContentWorkerIntegration:
    """Test Content Worker integration."""

    @pytest.mark.asyncio
    async def test_page_content_generation(self, mock_dependencies):
        """Test content generation for a single page."""
        from app.domain.wiki.nodes.content_worker import ContentWorkerNode
        
        node = ContentWorkerNode()
        
        # Mock LLM response
        mock_llm_response = MagicMock()
        mock_llm_response.content = "# Test Page\n\nThis is the generated content."
        
        with patch("app.domain.wiki.nodes.content_worker.get_default_llm", new_callable=AsyncMock) as mock_llm:
            mock_llm.return_value.ainvoke = AsyncMock(return_value=mock_llm_response)
            
            state = {
                "project_id": 1,
                "project_path": "/tmp/test",
                "current_page_index": 0,
                "pages_to_generate": [
                    {"id": "test-page", "title": "Test Page", "relevant_files": ["README.md"], "order": 0}
                ],
                "file_tree": "README.md",
                "force_regenerate": True,
                "generated_pages": [],
                "completed_pages": 0,
            }
            config = {"configurable": {"thread_id": "test"}}
            
            with patch.object(node, "_gather_file_context", new_callable=AsyncMock) as mock_gather:
                mock_gather.return_value = {"README.md": "# Test"}
                
                with patch.object(node, "_check_existing_page", new_callable=AsyncMock) as mock_check:
                    mock_check.return_value = False
                    
                    result = await node(state, config)
                    
                    assert "generated_pages" in result
                    assert len(result["generated_pages"]) == 1
                    assert result["current_page_index"] == 1


@pytest.mark.skip(reason="Module deleted in schema migration")
class TestWikiServiceIntegration:
    """Test WikiService integration with Agent engine."""

    @pytest.mark.asyncio
    async def test_service_uses_agent_by_default(self, mock_dependencies):
        """Test that service uses Agent mode by default."""
        from app.domain.wiki.service import WikiService
        
        service = WikiService()
        
        with patch.object(service, "_generate_wiki_via_agent", new_callable=AsyncMock) as mock_agent:
            mock_agent.return_value = []
            
            await service.generate_wiki(
                project_id=1,
                topic="Test",
                # use_agent defaults to True
            )
            
            mock_agent.assert_called_once()

    @pytest.mark.asyncio
    async def test_service_agent_fallback(self, mock_dependencies):
        """Test service falls back to direct when Agent fails."""
        from app.domain.wiki.service import WikiService
        
        service = WikiService()
        
        # Mock agent to fail
        with patch.object(service, "_generate_wiki_via_agent", new_callable=AsyncMock) as mock_agent:
            mock_agent.side_effect = Exception("Agent initialization failed")
            
            # Mock direct to succeed
            with patch.object(service, "_generate_wiki_direct", new_callable=AsyncMock) as mock_direct:
                mock_direct.return_value = []
                
                # Should try agent first, then fall back to direct
                result = await service.generate_wiki(
                    project_id=1,
                    topic="Test",
                    use_agent=True,
                )
                
                mock_agent.assert_called_once()
                mock_direct.assert_called_once()


@pytest.mark.skip(reason="Module deleted in schema migration")
class TestEmbeddedModeTaskExecution:
    """Test task execution in Embedded Mode (LocalCelery)."""

    def test_wiki_task_is_local_task(self):
        """Verify wiki task is a LocalTask in embedded mode."""
        from app.domain.wiki.tasks import generate_wiki_task
        from app.infrastructure.queue.celery import LocalTask
        
        assert isinstance(generate_wiki_task, LocalTask)
        assert generate_wiki_task.name == "wiki_generate"

    @pytest.mark.asyncio
    async def test_wiki_task_execution(self):
        """Test wiki task execution in embedded mode."""
        from app.domain.wiki.tasks import generate_wiki_task
        from app.infrastructure.queue.celery import LocalAsyncResult
        
        with patch("app.domain.wiki.tasks.wiki_service.generate_wiki", new_callable=AsyncMock) as mock_service:
            with patch("app.domain.wiki.tasks.activity_monitor") as mock_monitor:
                mock_monitor.start_run = AsyncMock()
                mock_monitor.update_agent_state = AsyncMock()
                mock_monitor.end_run = AsyncMock()
                
                # Execute task directly (sync wrapper)
                result = generate_wiki_task.delay(
                    project_id=1,
                    topic="Test",
                    use_agent=True,
                )
                
                # Should return LocalAsyncResult
                assert isinstance(result, LocalAsyncResult)
                
                # Wait for completion
                task_result = await result.get(timeout=10)
                
                assert "Wiki generated" in task_result


@pytest.mark.skip(reason="Module deleted in schema migration")
class TestWikiAgentConfigValidation:
    """Test Wiki Agent configuration validation."""

    def test_yaml_config_valid(self):
        """Test YAML configuration is valid and complete."""
        import yaml
        from app.core.engine.schemas import AgentConfig
        
        with open("app/config/agents/wiki_agent.yml") as f:
            raw_config = yaml.safe_load(f)
        
        # Should validate against AgentConfig schema
        config = AgentConfig(**raw_config)
        
        assert config.name == "WikiAgent"
        assert config.version == "1.0.0"
        assert len(config.nodes) == 4
        assert len(config.edges) == 4

    def test_node_paths_exist(self):
        """Test that all node paths can be imported."""
        import yaml
        
        with open("app/config/agents/wiki_agent.yml") as f:
            config = yaml.safe_load(f)
        
        for node in config["nodes"]:
            path = node["path"]
            module_path, obj_name = path.rsplit(".", 1)
            
            try:
                module = __import__(module_path, fromlist=[obj_name])
                obj = getattr(module, obj_name)
                assert obj is not None, f"Could not import {path}"
            except ImportError as e:
                pytest.fail(f"Failed to import {path}: {e}")


@pytest.mark.skip(reason="Module deleted in schema migration")
class TestErrorRecovery:
    """Test error recovery and resilience."""

    @pytest.mark.asyncio
    async def test_structure_worker_fallback_on_llm_error(self, mock_dependencies):
        """Test structure worker falls back to default structure on LLM error."""
        from app.domain.wiki.nodes.structure_worker import StructureWorkerNode
        
        node = StructureWorkerNode()
        
        with patch("app.domain.wiki.nodes.structure_worker.get_default_llm", new_callable=AsyncMock) as mock_llm:
            mock_llm.return_value.ainvoke = AsyncMock(side_effect=Exception("LLM error"))
            
            with patch("app.domain.wiki.nodes.structure_worker.evocloud_manager.get_project_by_id", new_callable=AsyncMock) as mock_cloud:
                mock_cloud.return_value = {"path": "/tmp/test"}
                
                with patch.object(node, "_get_file_tree", return_value=""):
                    with patch.object(node, "_read_file_safe", return_value=""):
                        state = {
                            "execution_ticket": {
                                "parameters": {"project_id": 1}
                            }
                        }
                        config = {"configurable": {"thread_id": "test"}}
                        
                        result = await node(state, config)
                        
                        # Should have fallback structure
                        assert "wiki_structure" in result
                        assert len(result["wiki_structure"]) == 3  # Default pages
                        assert result["structure_validated"] is False

    @pytest.mark.asyncio
    async def test_content_worker_error_handling(self, mock_dependencies):
        """Test content worker handles generation errors gracefully."""
        from app.domain.wiki.nodes.content_worker import ContentWorkerNode
        
        node = ContentWorkerNode()
        
        with patch("app.domain.wiki.nodes.content_worker.get_default_llm", new_callable=AsyncMock) as mock_llm:
            mock_llm.return_value.ainvoke = AsyncMock(side_effect=Exception("Generation failed"))
            
            state = {
                "project_id": 1,
                "project_path": "/tmp/test",
                "current_page_index": 0,
                "pages_to_generate": [
                    {"id": "test", "title": "Test Page", "relevant_files": [], "order": 0}
                ],
                "file_tree": "",
                "force_regenerate": True,
                "generated_pages": [],
                "completed_pages": 0,
            }
            config = {"configurable": {"thread_id": "test"}}
            
            with patch.object(node, "_gather_file_context", new_callable=AsyncMock) as mock_gather:
                mock_gather.return_value = {}
                
                result = await node(state, config)
                
                # Should still progress despite error
                assert result["current_page_index"] == 1
                assert len(result["generated_pages"]) == 1
                # Content should indicate error
                assert "Error" in result["generated_pages"][0]["content"]


# Mark all tests as requiring no external services
pytestmark = [
    pytest.mark.asyncio,
    pytest.mark.integration,
    pytest.mark.no_external_services,
]
