"""
Core unit tests for Wiki Agent - Simplified version.

Note: These tests verify the refactored Wiki Agent using core AgentEngine.
"""
import pytest
import os


# Ensure embedded mode (SQLite + LanceDB + LocalCelery, no external dependencies)
os.environ['EMBEDDED_MODE'] = 'true'


class TestWikiAgentConfig:
    """Test Wiki Agent YAML configuration."""

    def test_yaml_config_valid(self):
        """Test YAML configuration is valid."""
        import yaml
        
        config_path = os.path.join(
            os.path.dirname(__file__), 
            '..', '..', '..', '..', 
            'app', 'config', 'agents', 'wiki_agent.yml'
        )
        
        with open(config_path) as f:
            config = yaml.safe_load(f)
        
        assert config["name"] == "WikiAgent"
        assert config["version"] == "1.0.0"
        assert len(config["nodes"]) == 4
        assert len(config["edges"]) == 4

    def test_nodes_defined(self):
        """Test all required nodes are defined."""
        import yaml
        
        config_path = os.path.join(
            os.path.dirname(__file__), 
            '..', '..', '..', '..', 
            'app', 'config', 'agents', 'wiki_agent.yml'
        )
        
        with open(config_path) as f:
            config = yaml.safe_load(f)
        
        node_ids = [node["id"] for node in config["nodes"]]
        required = ["router", "wiki_structure_worker", "wiki_content_worker", "wiki_finish"]
        
        for node_id in required:
            assert node_id in node_ids, f"Missing node: {node_id}"


class TestWikiTools:
    """Test Wiki tools."""

    def test_tool_functions_exist(self):
        """Test tool functions are defined."""
        from app.domain.wiki.tools import (
            get_project_path,
            analyze_file_tree,
            read_project_file,
            read_directory_files,
        )
        
        # Functions exist
        assert callable(get_project_path)
        assert callable(analyze_file_tree)
        assert callable(read_project_file)
        assert callable(read_directory_files)

    def test_paths_to_tree_string(self):
        """Test tree string generation."""
        from app.domain.wiki.tools import _paths_to_tree_string
        
        paths = ["src/main.py", "src/utils.py", "tests/test.py"]
        tree = _paths_to_tree_string(paths)
        
        assert "src" in tree
        assert "main.py" in tree
        assert "tests" in tree


class TestAgentState:
    """Test AgentState reuse."""

    def test_wiki_state_is_agent_state(self):
        """Test WikiAgentState is just AgentState."""
        from app.domain.wiki.agent_state import WikiAgentState
        from app.core.engine.state import AgentState
        
        # Should be the same
        assert WikiAgentState is AgentState

    def test_wiki_page_content_defined(self):
        """Test WikiPageContent is defined."""
        from app.domain.wiki.agent_state import WikiPageContent
        
        # TypedDict exists
        assert WikiPageContent is not None


class TestEmbeddedMode:
    """Test Embedded Mode compatibility."""

    def test_celery_app_is_local(self):
        """Test that celery_app is LocalCelery."""
        from app.infrastructure.queue.celery import celery_app, LocalCelery
        from app.core.config import settings
        
        assert settings.EMBEDDED_MODE is True
        assert isinstance(celery_app, LocalCelery)

    def test_wiki_task_registered(self):
        """Test that wiki task can be registered."""
        from app.infrastructure.queue.celery import LocalTask
        
        async def sample_task(project_id: int, topic: str):
            return f"Wiki for {project_id}"
        
        task = LocalTask(sample_task, name="wiki_generate")
        assert task.name == "wiki_generate"


class TestWorkerNodes:
    """Test Worker nodes use AgentEngine."""

    def test_structure_worker_imports(self):
        """Test StructureWorker imports."""
        from app.domain.wiki.nodes.structure_worker import (
            StructureWorkerNode,
            structure_worker_node,
            structure_router,
        )
        
        assert StructureWorkerNode is not None
        assert structure_worker_node is not None
        assert callable(structure_router)

    def test_content_worker_imports(self):
        """Test ContentWorker imports."""
        from app.domain.wiki.nodes.content_worker import (
            ContentWorkerNode,
            content_worker_node,
            content_router,
        )
        
        assert ContentWorkerNode is not None
        assert content_worker_node is not None
        assert callable(content_router)

    def test_finish_node_imports(self):
        """Test FinishNode imports."""
        from app.domain.wiki.nodes.finish import WikiFinishNode, wiki_finish_node
        
        assert WikiFinishNode is not None
        assert wiki_finish_node is not None


class TestAgentEngine:
    """Test Wiki AgentEngine."""

    def test_agent_engine_import(self):
        """Test AgentEngine can be imported."""
        from app.domain.wiki.agent_engine import WikiAgentEngine, wiki_agent_engine
        
        assert WikiAgentEngine is not None
        assert wiki_agent_engine is not None

    def test_agent_engine_methods(self):
        """Test AgentEngine has required methods."""
        from app.domain.wiki.agent_engine import WikiAgentEngine
        
        engine = WikiAgentEngine()
        assert hasattr(engine, 'initialize')
        assert hasattr(engine, 'generate_wiki')


pytestmark = [
    pytest.mark.unit,
    pytest.mark.no_external_services,
]
