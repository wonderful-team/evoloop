"""
Tests for Routing Tools - Basic Functionality

This module tests the route_to tool functionality.
Note: Tool management is handled via agent_main.yaml and Supervisor's authorized_tools
parameter, not via hardcoded requirements in the routing layer.
"""
import pytest

from app.core.engine.tools.orchestration import route_to
from app.constants import RoutingTarget


class TestRouteToBasic:
    """Basic tests for route_to tool."""

    def test_route_to_basic_signal(self):
        """Test that route_to returns a valid route signal."""
        result = route_to.invoke({
            "target": RoutingTarget.WORKER,
            "reason": "Test routing"
        })
        
        assert isinstance(result, str)
        assert "[ROUTE_SIGNAL]" in result
        assert "worker" in result
        assert "Test routing" in result

    def test_route_to_with_context(self):
        """Test that route_to preserves custom context."""
        result = route_to.invoke({
            "target": RoutingTarget.DEEP_RESEARCHER,
            "reason": "Research task",
            "context": {"topic": "AI safety", "depth": "comprehensive"}
        })
        
        assert "topic" in result
        assert "AI safety" in result
        assert "depth" in result

    def test_route_to_with_authorized_tools(self):
        """Test that authorized_tools are included in signal."""
        tools = ["search_web", "browser_control", "read_file"]
        result = route_to.invoke({
            "target": RoutingTarget.DEEP_RESEARCHER,
            "reason": "Web research",
            "authorized_tools": tools
        })
        
        # Tools should be in the context
        assert "search_web" in result
        assert "browser_control" in result
        assert "authorized_tools" in result

    def test_route_to_with_skill_id(self):
        """Test that skill_id is included in result."""
        result = route_to.invoke({
            "target": RoutingTarget.DEEP_RESEARCHER,
            "reason": "Research",
            "skill_id": 123
        })
        
        assert "Skill ID: 123" in result

    def test_route_to_finish(self):
        """Test routing to finish."""
        result = route_to.invoke({
            "target": RoutingTarget.FINISH,
            "reason": "Task completed"
        })
        
        assert "finish" in result
        assert "Task completed" in result


class TestRouteToDifferentTargets:
    """Tests for routing to different targets."""

    def test_route_to_chat(self):
        """Test routing to chat."""
        result = route_to.invoke({
            "target": RoutingTarget.CHAT,
            "reason": "Need clarification"
        })
        
        assert "chat" in result

    def test_route_to_supervisor(self):
        """Test routing back to supervisor."""
        result = route_to.invoke({
            "target": RoutingTarget.SUPERVISOR,
            "reason": "Need re-planning"
        })
        
        assert "supervisor" in result

    def test_route_to_flash_brain(self):
        """Test routing to flash_brain."""
        result = route_to.invoke({
            "target": RoutingTarget.FLASH_BRAIN,
            "reason": "Quick lookup"
        })
        
        assert "flash_brain" in result


class TestRouteToEdgeCases:
    """Edge case tests for route_to."""

    def test_empty_context(self):
        """Test with empty context."""
        result = route_to.invoke({
            "target": RoutingTarget.WORKER,
            "reason": "Test",
            "context": {}
        })
        
        assert "[ROUTE_SIGNAL]" in result

    def test_none_context(self):
        """Test with None context."""
        result = route_to.invoke({
            "target": RoutingTarget.WORKER,
            "reason": "Test",
            "context": None
        })
        
        assert "[ROUTE_SIGNAL]" in result

    def test_empty_tools_list(self):
        """Test with empty authorized_tools."""
        result = route_to.invoke({
            "target": RoutingTarget.WORKER,
            "reason": "Test",
            "authorized_tools": []
        })
        
        assert "[ROUTE_SIGNAL]" in result
        # Should not include tools info when empty
        assert "authorized_tools" not in result or "[]" in result


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
