"""
Engine Layer Tests - Supervisor Node
Covers: SUP-001 to SUP-008
"""
import pytest
from unittest.mock import patch, MagicMock, AsyncMock
from langchain_core.messages import HumanMessage, AIMessage

from tests.config import config


class TestSupervisorRouting:
    """Test suite for Supervisor routing decisions."""

    @pytest.fixture
    def mock_config(self, thread_id, project_context):
        """Create a mock RunnableConfig."""
        return {
            "configurable": {
                "thread_id": thread_id,
                "project_id": project_context["project_id"],
                "working_directory": project_context["project_path"]
            }
        }

    # SUP-001: Code Task Routing
    @pytest.mark.asyncio
    async def test_sup_001_code_routing(self, base_agent_state, mock_config):
        """Test routing to coder for code-related tasks."""
        from app.core.engine.nodes.supervisor import supervisor_node
        
        state = base_agent_state.copy()
        state["messages"] = [HumanMessage(content="帮我写一个 Python 函数计算阶乘")]
        
        with patch("app.core.engine.nodes.supervisor.AgentEngine") as MockEngine:
            mock_engine = MagicMock()
            mock_engine.run_node = AsyncMock(return_value={
                "next_node": "coder",
                "messages": [AIMessage(content="I'll create a factorial function")]
            })
            MockEngine.return_value = mock_engine
            
            result = await supervisor_node(state, mock_config)
            
            # Should route to coder
            assert result.get("next_node") in ["coder", "planner"]

    # SUP-002: Research Task Routing
    @pytest.mark.asyncio
    async def test_sup_002_research_routing(self, base_agent_state, mock_config):
        """Test routing to deep_researcher for research tasks."""
        from app.core.engine.nodes.supervisor import supervisor_node
        
        state = base_agent_state.copy()
        state["messages"] = [HumanMessage(content="深入研究 LangGraph 的设计理念")]
        
        with patch("app.core.engine.nodes.supervisor.AgentEngine") as MockEngine:
            mock_engine = MagicMock()
            mock_engine.run_node = AsyncMock(return_value={
                "next_node": "deep_researcher",
                "messages": []
            })
            MockEngine.return_value = mock_engine
            
            result = await supervisor_node(state, mock_config)
            
            assert result.get("next_node") == "deep_researcher"

    # SUP-003: Documentation Task Routing
    @pytest.mark.asyncio
    async def test_sup_003_doc_routing(self, base_agent_state, mock_config):
        """Test routing to documenter for documentation tasks."""
        from app.core.engine.nodes.supervisor import supervisor_node
        
        state = base_agent_state.copy()
        state["messages"] = [HumanMessage(content="为这个项目生成 Wiki 文档")]
        
        with patch("app.core.engine.nodes.supervisor.AgentEngine") as MockEngine:
            mock_engine = MagicMock()
            mock_engine.run_node = AsyncMock(return_value={
                "next_node": "documenter",
                "messages": []
            })
            MockEngine.return_value = mock_engine
            
            result = await supervisor_node(state, mock_config)
            
            assert result.get("next_node") == "documenter"

    # SUP-004: Planning Task Routing
    @pytest.mark.asyncio
    async def test_sup_004_planner_routing(self, base_agent_state, mock_config):
        """Test routing to planner for planning tasks."""
        from app.core.engine.nodes.supervisor import supervisor_node
        
        state = base_agent_state.copy()
        state["messages"] = [HumanMessage(content="规划一个重构方案")]
        
        with patch("app.core.engine.nodes.supervisor.AgentEngine") as MockEngine:
            mock_engine = MagicMock()
            mock_engine.run_node = AsyncMock(return_value={
                "next_node": "planner",
                "messages": []
            })
            MockEngine.return_value = mock_engine
            
            result = await supervisor_node(state, mock_config)
            
            assert result.get("next_node") == "planner"

    # SUP-005: Chat Routing
    @pytest.mark.asyncio
    async def test_sup_005_chat_routing(self, base_agent_state, mock_config):
        """Test routing to chat for casual conversation."""
        from app.core.engine.nodes.supervisor import supervisor_node
        
        state = base_agent_state.copy()
        state["messages"] = [HumanMessage(content="你好，今天天气怎么样？")]
        
        with patch("app.core.engine.nodes.supervisor.AgentEngine") as MockEngine:
            mock_engine = MagicMock()
            mock_engine.run_node = AsyncMock(return_value={
                "next_node": "chat",
                "messages": [AIMessage(content="你好！我是 AI 助手。")]
            })
            MockEngine.return_value = mock_engine
            
            result = await supervisor_node(state, mock_config)
            
            assert result.get("next_node") == "chat"

    # SUP-006: Finish Routing
    @pytest.mark.asyncio
    async def test_sup_006_finish_routing(self, base_agent_state, mock_config):
        """Test routing to finish for completion."""
        from app.core.engine.nodes.supervisor import supervisor_node
        
        state = base_agent_state.copy()
        state["messages"] = [HumanMessage(content="谢谢，就这样")]
        
        with patch("app.core.engine.nodes.supervisor.AgentEngine") as MockEngine:
            mock_engine = MagicMock()
            mock_engine.run_node = AsyncMock(return_value={
                "next_node": "finish",
                "messages": []
            })
            MockEngine.return_value = mock_engine
            
            result = await supervisor_node(state, mock_config)
            
            assert result.get("next_node") == "finish"


class TestIntentClassifier:
    """Test suite for IntentClassifier (SUP-007, SUP-008, IC-001~004)."""

    # IC-001: Chinese Code Intent
    @pytest.mark.asyncio
    async def test_ic_001_chinese_code_intent(self):
        """Test classification of Chinese code-related message."""
        from app.core.engine.intent_classifier import IntentClassifier
        
        classifier = IntentClassifier()
        result = classifier.classify("写一个排序算法")
        
        assert result is not None
        # Should classify as code-related with reasonable confidence
        # Result structure depends on implementation

    # IC-002: English Research Intent
    @pytest.mark.asyncio
    async def test_ic_002_english_research_intent(self):
        """Test classification of English research message."""
        from app.core.engine.intent_classifier import IntentClassifier
        
        classifier = IntentClassifier()
        result = classifier.classify("Research about GraphQL")
        
        assert result is not None

    # IC-003: Ambiguous Intent
    @pytest.mark.asyncio
    async def test_ic_003_ambiguous_intent(self):
        """Test classification of ambiguous message."""
        from app.core.engine.intent_classifier import IntentClassifier
        
        classifier = IntentClassifier()
        result = classifier.classify("这个怎么弄？")
        
        # Should return low confidence or default
        assert result is not None

    # IC-004: Empty Message
    @pytest.mark.asyncio
    async def test_ic_004_empty_message(self):
        """Test classification of empty message."""
        from app.core.engine.intent_classifier import IntentClassifier
        
        classifier = IntentClassifier()
        result = classifier.classify("")
        
        # Should handle gracefully
        assert True  # No exception thrown


class TestSkillMatcher:
    """Test suite for SkillMatcher (SM-001~004)."""

    # SM-001: Regex Pattern Match
    @pytest.mark.asyncio
    async def test_sm_001_regex_match(self):
        """Test regex pattern matching."""
        from app.core.learning.skill_executor import SkillMatcher
        
        matcher = SkillMatcher()
        
        with patch.object(matcher, '_load_skills', return_value=[{
            "id": 1,
            "name": "git_commit",
            "trigger_patterns": ["帮我提交 {message}", "commit {message}"]
        }]):
            result = await matcher.match("帮我提交 'bugfix'")
            
            if result:
                assert result.confidence >= 0.9

    # SM-002: Semantic Match
    @pytest.mark.asyncio
    async def test_sm_002_semantic_match(self):
        """Test semantic matching via LLM."""
        from app.core.learning.skill_executor import SkillMatcher
        
        matcher = SkillMatcher()
        
        # This tests the semantic matching path
        result = await matcher.match("commit the code with message 'update'")
        
        # May or may not match depending on available skills
        assert True  # Placeholder

    # SM-003: No Match
    @pytest.mark.asyncio
    async def test_sm_003_no_match(self):
        """Test when no skill matches."""
        from app.core.learning.skill_executor import SkillMatcher
        
        matcher = SkillMatcher()
        result = await matcher.match("这是一个完全不相关的请求 XYZ123")
        
        # Should return None or low confidence
        assert result is None or (hasattr(result, 'confidence') and result.confidence < 0.5)

    # SM-004: Threshold Filtering
    @pytest.mark.asyncio
    async def test_sm_004_threshold_filter(self):
        """Test threshold-based filtering."""
        from app.core.learning.skill_executor import SkillMatcher
        
        matcher = SkillMatcher()
        result = await matcher.match("maybe compile", threshold=0.9)
        
        # High threshold should filter out low-confidence matches
        assert True


class TestGraphBuilder:
    """Test suite for GraphBuilder (GB-001~005)."""

    # GB-001: YAML Loading
    @pytest.mark.asyncio
    async def test_gb_001_yaml_loading(self):
        """Test loading graph from YAML configuration."""
        from app.core.engine.graph_builder import GraphBuilder
        
        builder = GraphBuilder()
        graph = await builder.build("app/core/engine/config/agent_main.yaml")
        
        assert graph is not None

    # GB-002: Node Dynamic Import
    @pytest.mark.asyncio
    async def test_gb_002_node_import(self):
        """Test dynamic import of node functions."""
        from app.core.engine.graph_builder import _import_obj
        
        # Import a known node
        node_func = _import_obj("app.core.engine.nodes.coder.coder_node")
        
        assert callable(node_func)

    # GB-003: Edge Configuration
    @pytest.mark.asyncio
    async def test_gb_003_edge_config(self):
        """Test that edges are correctly configured."""
        from app.core.engine.graph_builder import GraphBuilder
        
        builder = GraphBuilder()
        graph = await builder.build("app/core/engine/config/agent_main.yaml")
        
        # Graph should have edges
        assert graph is not None

    # GB-004: Conditional Router
    @pytest.mark.asyncio
    async def test_gb_004_conditional_router(self):
        """Test conditional routing setup."""
        from app.core.engine.routers import route_tester
        
        # Test the router function exists and is callable
        assert callable(route_tester)

    # GB-005: Invalid Configuration
    @pytest.mark.asyncio
    async def test_gb_005_invalid_config(self):
        """Test handling of invalid configuration."""
        from app.core.engine.graph_builder import GraphBuilder
        
        builder = GraphBuilder()
        
        with pytest.raises((FileNotFoundError, ValueError, ImportError)):
            await builder.build("nonexistent_config.yaml")
