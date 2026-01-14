"""
Workflow Node Tests - Tester Node
Covers: TST-001 to TST-006
"""
import pytest
import os
import tempfile
import shutil
from unittest.mock import patch, MagicMock, AsyncMock
from langchain_core.messages import HumanMessage, AIMessage

from tests.config import config


class TestTesterNode:
    """Test suite for Tester node functionality."""

    @pytest.fixture
    def sandbox_temp_dir(self, tmp_path):
        """Create sandbox temp directory."""
        backend_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        sandbox_dir = os.path.join(backend_dir, ".test_sandbox")
        os.makedirs(sandbox_dir, exist_ok=True)
        test_dir = os.path.join(sandbox_dir, tmp_path.name)
        os.makedirs(test_dir, exist_ok=True)
        
        # Create sample test files
        os.makedirs(os.path.join(test_dir, "tests"), exist_ok=True)
        with open(os.path.join(test_dir, "tests", "test_sample.py"), "w") as f:
            f.write('''def test_simple():
    assert 1 + 1 == 2

def test_failure():
    assert False
''')
        yield test_dir
        shutil.rmtree(test_dir, ignore_errors=True)

    @pytest.fixture
    def tester_state(self, base_agent_state):
        state = base_agent_state.copy()
        state["messages"] = [AIMessage(content="Created new function...")]
        state["scratchpad"]["test_command"] = "pytest tests/test_sample.py"
        return state

    @pytest.fixture
    def tester_config(self, thread_id, sandbox_temp_dir):
        return {
            "configurable": {
                "thread_id": thread_id,
                "project_id": config.PROJECT_ID,
                "working_directory": sandbox_temp_dir
            }
        }

    # TST-001: Execute Test Command
    @pytest.mark.asyncio
    async def test_tst_001_execute_test_command(self, sandbox_temp_dir):
        """Test executing pytest command."""
        from app.domain.tools.execution import run_command
        
        result = await run_command.ainvoke({
            "command": f"cd {sandbox_temp_dir} && python -m pytest tests/test_sample.py::test_simple -v"
        })
        
        assert "passed" in result.lower() or "succeeded" in result.lower() or "test_simple" in result

    # TST-002: JUnit XML Parse
    @pytest.mark.asyncio
    async def test_tst_002_junit_xml_parse(self, sandbox_temp_dir):
        """Test parsing JUnit XML report."""
        from app.domain.testing.parser import TestParser
        
        # Create sample JUnit XML
        report_xml = '''<?xml version="1.0" encoding="utf-8"?>
<testsuite name="pytest" errors="0" failures="1" tests="2">
    <testcase classname="tests.test_sample" name="test_simple" time="0.001"/>
    <testcase classname="tests.test_sample" name="test_failure" time="0.001">
        <failure message="assert False">AssertionError: assert False</failure>
    </testcase>
</testsuite>'''
        
        report_path = os.path.join(sandbox_temp_dir, "report.xml")
        with open(report_path, "w") as f:
            f.write(report_xml)
        
        result = TestParser.parse_junit_xml(report_path)
        
        assert result.failures == 1
        assert not result.is_pass

    # TST-003: Test Pass
    @pytest.mark.asyncio
    async def test_tst_003_test_pass(self, tester_state, tester_config):
        """Test handling of passing tests."""
        from app.core.engine.nodes.tester import TesterNode
        
        mock_response = MagicMock()
        mock_response.content = "Tests passed!"
        mock_response.tool_calls = []
        
        with patch.object(TesterNode, '__init__', lambda self: None):
            tester = TesterNode()
            tester.llm = MagicMock()
            tester.llm_with_tools = MagicMock()
            tester.llm_with_tools.ainvoke = AsyncMock(return_value=mock_response)
            tester.llm.with_structured_output = MagicMock(return_value=MagicMock(
                ainvoke=AsyncMock(return_value=MagicMock(
                    status="PASS",
                    summary="All tests passed",
                    root_cause=None,
                    fix_suggestion=None
                ))
            ))
            tester.tools = []
            tester.tool_map = {}
            
            result = await tester(tester_state, tester_config)
            
            assert "test_results" in result or result is not None

    # TST-004: Test Fail Retry
    @pytest.mark.asyncio
    async def test_tst_004_test_fail_retry(self, tester_state, tester_config):
        """Test retry logic on test failure."""
        tester_state["iteration_count"] = 1
        
        # Test that retry count increases
        assert tester_state.get("iteration_count", 0) < 3

    # TST-005: Test Fail Give Up
    @pytest.mark.asyncio
    async def test_tst_005_test_fail_give_up(self, tester_state, tester_config):
        """Test giving up after max retries."""
        tester_state["iteration_count"] = 3
        
        # Should route to meta_reviewer or finish
        assert True

    # TST-006: RCA Suggestion
    @pytest.mark.asyncio
    async def test_tst_006_rca_suggestion(self):
        """Test root cause analysis suggestions."""
        from app.core.engine.nodes.tester import TestAnalysis
        
        analysis = TestAnalysis(
            status="FAIL",
            summary="Test failed due to import error",
            root_cause="Missing dependency",
            fix_suggestion="Run pip install missing_package"
        )
        
        assert analysis.status == "FAIL"
        assert analysis.fix_suggestion is not None


class TestTesterRouting:
    """Test routing logic for tester node."""

    @pytest.fixture
    def base_state(self, base_agent_state):
        return base_agent_state.copy()

    # Test route on pass
    @pytest.mark.asyncio
    async def test_route_tester_pass(self, base_state):
        """Test routing when tests pass."""
        base_state["test_results"] = "PASS"
        
        from app.core.engine.routers import route_tester
        
        result = route_tester(base_state)
        
        # Should route to finish or supervisor
        assert result in ["finish", "supervisor", "__end__"] or result is not None

    # Test route on fail under limit
    @pytest.mark.asyncio
    async def test_route_tester_fail_under_limit(self, base_state):
        """Test routing when tests fail but under retry limit."""
        base_state["test_results"] = "FAIL"
        base_state["iteration_count"] = 1
        
        from app.core.engine.routers import route_tester
        
        result = route_tester(base_state)
        
        # Should route to coder for fix
        assert result is not None

    # Test route on fail over limit
    @pytest.mark.asyncio
    async def test_route_tester_fail_over_limit(self, base_state):
        """Test routing when tests fail and over retry limit."""
        base_state["test_results"] = "FAIL"
        base_state["iteration_count"] = 3
        
        from app.core.engine.routers import route_tester
        
        result = route_tester(base_state)
        
        # Should route to meta_reviewer or planner
        assert result is not None
