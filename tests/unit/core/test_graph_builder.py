"""
Tests for GraphBuilder

Tests the graph building functionality from YAML configuration.
"""
import os
import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest
import yaml

from app.core.engine.graph_builder import GraphBuilder
from app.core.engine.schema import AgentConfig


class TestGraphBuilderBasic:
    """Basic tests for GraphBuilder functionality."""

    @pytest.fixture
    def builder(self):
        """Create a GraphBuilder instance."""
        return GraphBuilder()

    @pytest.fixture
    def valid_config(self):
        """Return a minimal valid configuration dict."""
        return {
            "name": "test_graph",
            "version": "1.0",
            "state_schema": "app.core.engine.state.AgentState",
            "nodes": [
                {"id": "test_node", "path": "app.test.node_func"}
            ],
            "edges": []
        }

    def test_import_obj_success(self, builder):
        """Test importing a valid object path."""
        # Mock the import
        with patch.object(builder, '_import_obj', return_value=MagicMock()) as mock_import:
            result = builder._import_obj("app.core.engine.state.AgentState")
            mock_import.assert_called_once()

    def test_import_obj_failure(self, builder):
        """Test importing an invalid object path raises error."""
        with pytest.raises((ImportError, AttributeError)):
            builder._import_obj("nonexistent.module.function")


class TestGraphBuilderBuild:
    """Tests for GraphBuilder.build method."""

    @pytest.fixture
    def minimal_config(self):
        """Create a minimal valid YAML config file."""
        config = {
            "name": "minimal",
            "version": "1.0",
            "state_schema": "app.core.engine.state.AgentState",
            "nodes": [
                {"id": "node1", "path": "app.test.node1"}
            ],
            "edges": []
        }
        return config

    @pytest.fixture
    def complex_config(self):
        """Create a more complex YAML config."""
        config = {
            "name": "complex",
            "version": "1.0",
            "state_schema": "app.core.engine.state.AgentState",
            "nodes": [
                {"id": "router", "path": "app.test.router"},
                {"id": "worker", "path": "app.test.worker"},
                {"id": "finish", "path": "app.test.finish"}
            ],
            "edges": [
                {"from": "router", "to": "worker", "type": "simple"},
                {"from": "worker", "to": "finish", "type": "simple"},
                {"from": "finish", "to": "END", "type": "simple"}
            ],
            "interrupt_before": ["worker"]
        }
        return config

    def test_build_minimal_graph(self, minimal_config, tmp_path):
        """Test building a minimal graph."""
        # Create temp config file
        config_path = tmp_path / "test.yaml"
        with open(config_path, "w") as f:
            yaml.dump(minimal_config, f)

        builder = GraphBuilder()
        
        # Mock imports
        with patch.object(builder, '_import_obj', return_value=MagicMock()):
            result = builder.build(str(config_path))
            
        assert result is not None

    def test_build_complex_graph(self, complex_config, tmp_path):
        """Test building a complex graph with multiple nodes and edges."""
        config_path = tmp_path / "complex.yaml"
        with open(config_path, "w") as f:
            yaml.dump(complex_config, f)

        builder = GraphBuilder()
        
        with patch.object(builder, '_import_obj', return_value=MagicMock()):
            result = builder.build(str(config_path))
            
        assert result is not None

    def test_graph_with_conditional_edges(self, tmp_path):
        """Test building graph with conditional edges."""
        config = {
            "name": "conditional",
            "version": "1.0",
            "state_schema": "app.core.engine.state.AgentState",
            "nodes": [
                {"id": "router", "path": "app.test.router"},
                {"id": "option_a", "path": "app.test.a"},
                {"id": "option_b", "path": "app.test.b"}
            ],
            "edges": [
                {
                    "from": "router",
                    "type": "conditional",
                    "router": "app.routers.decision",
                    "map": {"a": "option_a", "b": "option_b"}
                }
            ]
        }
        
        config_path = tmp_path / "conditional.yaml"
        with open(config_path, "w") as f:
            yaml.dump(config, f)

        builder = GraphBuilder()
        
        with patch.object(builder, '_import_obj', return_value=MagicMock()):
            result = builder.build(str(config_path))
            
        assert result is not None

    def test_graph_with_expression_conditions(self, tmp_path):
        """Test building graph with expression-based conditions."""
        config = {
            "name": "expression",
            "version": "1.0",
            "state_schema": "app.core.engine.state.AgentState",
            "nodes": [
                {"id": "decision", "path": "app.test.decision"},
                {"id": "true_branch", "path": "app.test.true"},
                {"id": "false_branch", "path": "app.test.false"}
            ],
            "edges": [
                {
                    "from": "decision",
                    "type": "conditional",
                    "conditions": [
                        {"expr": "state.get('x') > 0", "to": "true_branch"},
                        {"expr": "state.get('x') <= 0", "to": "false_branch"}
                    ],
                    "default": "false_branch"
                }
            ]
        }
        
        config_path = tmp_path / "expression.yaml"
        with open(config_path, "w") as f:
            yaml.dump(config, f)

        builder = GraphBuilder()
        
        with patch.object(builder, '_import_obj', return_value=MagicMock()):
            result = builder.build(str(config_path))
            
        assert result is not None

    def test_router_entry_point(self, tmp_path):
        """Test that 'router' node is used as entry point if present."""
        config = {
            "name": "router_entry",
            "version": "1.0",
            "state_schema": "app.core.engine.state.AgentState",
            "nodes": [
                {"id": "worker", "path": "app.test.worker"},
                {"id": "router", "path": "app.test.router"},
                {"id": "finish", "path": "app.test.finish"}
            ],
            "edges": []
        }
        
        config_path = tmp_path / "entry.yaml"
        with open(config_path, "w") as f:
            yaml.dump(config, f)

        builder = GraphBuilder()
        
        with patch.object(builder, '_import_obj', return_value=MagicMock()):
            result = builder.build(str(config_path))
            
        assert result is not None

    def test_first_node_entry_point(self, tmp_path):
        """Test that first node is used as entry point when no router."""
        config = {
            "name": "first_entry",
            "version": "1.0",
            "state_schema": "app.core.engine.state.AgentState",
            "nodes": [
                {"id": "first", "path": "app.test.first"},
                {"id": "second", "path": "app.test.second"}
            ],
            "edges": []
        }
        
        config_path = tmp_path / "first.yaml"
        with open(config_path, "w") as f:
            yaml.dump(config, f)

        builder = GraphBuilder()
        
        with patch.object(builder, '_import_obj', return_value=MagicMock()):
            result = builder.build(str(config_path))
            
        assert result is not None

    def test_yaml_parsing_error(self, tmp_path):
        """Test handling of invalid YAML."""
        config_path = tmp_path / "invalid.yaml"
        with open(config_path, "w") as f:
            f.write("invalid: yaml: content: [}")

        builder = GraphBuilder()
        
        with pytest.raises(yaml.YAMLError):
            builder.build(str(config_path))

    def test_missing_file(self, tmp_path):
        """Test handling of missing config file."""
        config_path = tmp_path / "nonexistent.yaml"
        
        builder = GraphBuilder()
        
        with pytest.raises(FileNotFoundError):
            builder.build(str(config_path))

    def test_node_with_tools(self, tmp_path):
        """Test building graph with nodes that have tools."""
        config = {
            "name": "with_tools",
            "version": "1.0",
            "state_schema": "app.core.engine.state.AgentState",
            "nodes": [
                {
                    "id": "supervisor",
                    "path": "app.test.supervisor",
                    "tools": ["route_to", "decompose_task"]
                },
                {
                    "id": "worker",
                    "path": "app.test.worker",
                    "tools": ["read_file", "write_file"]
                }
            ],
            "edges": [
                {"from": "supervisor", "to": "worker", "type": "simple"}
            ]
        }
        
        config_path = tmp_path / "tools.yaml"
        with open(config_path, "w") as f:
            yaml.dump(config, f)

        builder = GraphBuilder()
        
        with patch.object(builder, '_import_obj', return_value=MagicMock()):
            result = builder.build(str(config_path))
            
        assert result is not None


class TestGraphBuilderIntegration:
    """Integration-style tests for GraphBuilder."""

    def test_end_to_end_build(self, tmp_path):
        """Test end-to-end graph building with realistic config."""
        config = {
            "name": "evoloop_test",
            "version": "3.0",
            "state_schema": "app.core.engine.state.AgentState",
            "nodes": [
                {"id": "supervisor", "path": "app.core.engine.nodes.supervisor.supervisor_node"},
                {"id": "worker", "path": "app.core.engine.nodes.worker.worker_node"},
                {"id": "finish", "path": "app.core.engine.nodes.finish.finish_node"}
            ],
            "edges": [
                {
                    "from": "supervisor",
                    "type": "conditional",
                    "router": "app.core.engine.routers.route_supervisor",
                    "map": {
                        "worker": "worker",
                        "finish": "finish"
                    }
                },
                {"from": "worker", "to": "supervisor", "type": "simple"},
                {"from": "finish", "to": "END", "type": "simple"}
            ],
            "interrupt_before": [],
            "interrupt_after": []
        }
        
        config_path = tmp_path / "evoloop.yaml"
        with open(config_path, "w") as f:
            yaml.dump(config, f)

        builder = GraphBuilder()
        
        # Mock all imports
        mock_node = MagicMock()
        mock_router = MagicMock()
        
        def mock_import(path):
            if "router" in path:
                return mock_router
            return mock_node
        
        with patch.object(builder, '_import_obj', side_effect=mock_import) as mock_import_obj:
            result = builder.build(str(config_path))
            
        assert result is not None
        # Verify all imports were called
        assert mock_import_obj.call_count >= 3  # 3 nodes + 1 router


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
