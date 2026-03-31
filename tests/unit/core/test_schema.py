"""
Tests for Graph Configuration Schema

Tests the Pydantic models for agent graph configuration validation.
"""
import pytest
from pydantic import ValidationError

from app.core.engine.schema import NodeConfig, EdgeConfig, AgentConfig


class TestNodeConfig:
    """Tests for NodeConfig validation."""

    def test_valid_node_config(self):
        """Test creating a valid node config."""
        node = NodeConfig(
            id="worker",
            path="app.core.engine.nodes.worker.worker_node",
            type="function"
        )
        assert node.id == "worker"
        assert node.path == "app.core.engine.nodes.worker.worker_node"
        assert node.type == "function"

    def test_node_config_with_tools(self):
        """Test node config with tool list."""
        node = NodeConfig(
            id="supervisor",
            path="app.core.engine.nodes.supervisor.supervisor_node",
            tools=["route_to", "decompose_task"]
        )
        assert node.tools == ["route_to", "decompose_task"]

    def test_node_config_with_config(self):
        """Test node config with custom config."""
        node = NodeConfig(
            id="custom",
            path="some.path.node",
            config={"key": "value", "number": 42}
        )
        assert node.config["key"] == "value"
        assert node.config["number"] == 42

    def test_missing_path_raises_error(self):
        """Test that missing path raises validation error."""
        with pytest.raises(ValidationError) as exc_info:
            NodeConfig(id="test", path=None)
        
        assert "missing 'path'" in str(exc_info.value)

    def test_path_property(self):
        """Test that path property works correctly."""
        node = NodeConfig(
            id="test",
            path="app.test.node"
        )
        # path property should return xpath
        assert node.path == "app.test.node"


class TestEdgeConfig:
    """Tests for EdgeConfig validation."""

    def test_simple_edge(self):
        """Test creating a simple edge."""
        edge = EdgeConfig(**{
            "from": "supervisor",
            "to": "worker",
            "type": "simple"
        })
        assert edge.from_node == "supervisor"
        assert edge.to_node == "worker"
        assert edge.type == "simple"

    def test_simple_edge_missing_to_raises_error(self):
        """Test that simple edge without 'to' raises error."""
        with pytest.raises(ValidationError) as exc_info:
            EdgeConfig(**{
                "from": "start",
                "type": "simple"
            })
        
        assert "missing 'to'" in str(exc_info.value)

    def test_conditional_edge_with_router(self):
        """Test conditional edge with router function."""
        edge = EdgeConfig(**{
            "from": "router",
            "type": "conditional",
            "router": "app.routers.my_router",
            "map": {"condition_a": "node_a", "condition_b": "node_b"}
        })
        assert edge.router == "app.routers.my_router"
        assert edge.map["condition_a"] == "node_a"

    def test_conditional_edge_with_conditions(self):
        """Test conditional edge with expression conditions."""
        edge = EdgeConfig(**{
            "from": "decision",
            "type": "conditional",
            "conditions": [
                {"expr": "state.get('x') > 0", "to": "positive"},
                {"expr": "state.get('x') <= 0", "to": "non_positive"}
            ],
            "default": "default_node"
        })
        assert len(edge.conditions) == 2
        assert edge.default == "default_node"

    def test_conditional_edge_missing_router_and_conditions(self):
        """Test that conditional edge without router or conditions raises error."""
        with pytest.raises(ValidationError) as exc_info:
            EdgeConfig(**{
                "from": "start",
                "type": "conditional"
            })
        
        error_msg = str(exc_info.value).lower()
        assert "router" in error_msg or "conditions" in error_msg

    def test_field_aliases(self):
        """Test that field aliases work correctly."""
        edge = EdgeConfig(**{"from": "start", "to": "end", "type": "simple"})
        assert edge.from_node == "start"
        assert edge.to_node == "end"


class TestAgentConfig:
    """Tests for AgentConfig validation."""

    def test_minimal_valid_config(self):
        """Test creating a minimal valid agent config."""
        config = AgentConfig(
            name="test_agent",
            version="1.0",
            nodes=[
                NodeConfig(id="start", path="app.nodes.start")
            ],
            edges=[]
        )
        assert config.name == "test_agent"
        assert config.version == "1.0"
        assert config.state_schema == "app.core.engine.state.AgentState"

    def test_full_config(self):
        """Test creating a full agent config with all features."""
        config = AgentConfig(
            name="full_agent",
            version="2.0",
            state_schema="custom.state.Schema",
            nodes=[
                NodeConfig(id="router", path="app.nodes.router"),
                NodeConfig(id="worker", path="app.nodes.worker")
            ],
            edges=[
                EdgeConfig(**{"from": "router", "to": "worker", "type": "simple"})
            ],
            interrupt_before=["worker"],
            interrupt_after=["router"]
        )
        assert len(config.nodes) == 2
        assert len(config.edges) == 1
        assert config.interrupt_before == ["worker"]
        assert config.interrupt_after == ["router"]

    def test_edge_to_unknown_node_raises_error(self):
        """Test that edge to unknown node raises error."""
        with pytest.raises(ValidationError) as exc_info:
            AgentConfig(
                name="test",
                version="1.0",
                nodes=[
                    NodeConfig(id="start", path="app.nodes.start")
                ],
                edges=[
                    EdgeConfig(**{"from": "start", "to": "unknown", "type": "simple"})
                ]
            )
        
        assert "unknown node" in str(exc_info.value).lower()

    def test_edge_from_unknown_node_raises_error(self):
        """Test that edge from unknown node raises error."""
        with pytest.raises(ValidationError) as exc_info:
            AgentConfig(
                name="test",
                version="1.0",
                nodes=[
                    NodeConfig(id="start", path="app.nodes.start")
                ],
                edges=[
                    EdgeConfig(**{"from": "unknown", "to": "start", "type": "simple"})
                ]
            )
        
        assert "unknown node" in str(exc_info.value).lower()

    def test_conditional_edge_branch_to_unknown_node(self):
        """Test that conditional edge branch to unknown node raises error."""
        with pytest.raises(ValidationError) as exc_info:
            AgentConfig(
                name="test",
                version="1.0",
                nodes=[
                    NodeConfig(id="router", path="app.nodes.router")
                ],
                edges=[
                    EdgeConfig(**{
                        "from": "router",
                        "type": "conditional",
                        "conditions": [{"expr": "True", "to": "unknown_node"}]
                    })
                ]
            )
        
        assert "unknown node" in str(exc_info.value).lower()

    def test_router_map_to_unknown_node(self):
        """Test that router map to unknown node raises error."""
        with pytest.raises(ValidationError) as exc_info:
            AgentConfig(
                name="test",
                version="1.0",
                nodes=[
                    NodeConfig(id="router", path="app.nodes.router")
                ],
                edges=[
                    EdgeConfig(**{
                        "from": "router",
                        "type": "conditional",
                        "router": "app.routers.test",
                        "map": {"result": "unknown_node"}
                    })
                ]
            )
        
        assert "unknown node" in str(exc_info.value).lower()

    def test_default_edge_to_unknown_node(self):
        """Test that default edge to unknown node raises error."""
        with pytest.raises(ValidationError) as exc_info:
            AgentConfig(
                name="test",
                version="1.0",
                nodes=[
                    NodeConfig(id="router", path="app.nodes.router")
                ],
                edges=[
                    EdgeConfig(**{
                        "from": "router",
                        "type": "conditional",
                        "conditions": [{"expr": "True", "to": "router"}],
                        "default": "unknown_default"
                    })
                ]
            )
        
        assert "unknown node" in str(exc_info.value).lower()

    def test_end_node_is_always_valid(self):
        """Test that END is always a valid edge target."""
        config = AgentConfig(
            name="test",
            version="1.0",
            nodes=[
                NodeConfig(id="worker", path="app.nodes.worker")
            ],
            edges=[
                EdgeConfig(**{"from": "worker", "to": "END", "type": "simple"})
            ]
        )
        # Should not raise
        assert config.edges[0].to_node == "END"

    def test_multiple_nodes_and_edges(self):
        """Test complex graph with multiple nodes and edges."""
        config = AgentConfig(
            name="complex",
            version="1.0",
            nodes=[
                NodeConfig(id="supervisor", path="app.nodes.supervisor"),
                NodeConfig(id="worker", path="app.nodes.worker"),
                NodeConfig(id="aggregator", path="app.nodes.aggregator"),
                NodeConfig(id="finish", path="app.nodes.finish")
            ],
            edges=[
                EdgeConfig(**{"from": "supervisor", "to": "worker", "type": "simple"}),
                EdgeConfig(**{"from": "worker", "to": "aggregator", "type": "simple"}),
                EdgeConfig(**{"from": "aggregator", "to": "finish", "type": "simple"}),
                EdgeConfig(**{"from": "finish", "to": "END", "type": "simple"})
            ]
        )
        assert len(config.nodes) == 4
        assert len(config.edges) == 4


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
