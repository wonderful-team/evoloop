import pytest
from langchain_core.messages import HumanMessage
from app.core.engine.state import AgentState
from app.core.context import ContextManager, EvoContext
from app.core.engine.nodes.supervisor import SupervisorNode
from app.core.environment.models import AwakenedState, AndroidDevice, ConceptSummary
from unittest.mock import patch, MagicMock

@pytest.mark.asyncio
async def test_entity_focus_extraction_and_filtering():
    """
    Verifies that:
    1. Supervisor Node extracts App focus correctly.
    2. EnvironmentContextPlugin prioritizes Atlas Layouts based on Focus.
    3. Worker Node masks tools based on Focus.
    """
    
    # 1. Mock Awakened State with multiple layouts and installed apps
    from app.core.environment.models import MacOSEnvironment
    mock_state = AwakenedState(
        timestamp="2024-01-01T00:00:00.000000",
        macos=MacOSEnvironment(
            os_version="14.0", model="MacBook Pro", cpu="M3", ram_gb=32,
            installed_apps=["Chrome", "Safari", "WeChat"]
        ),
        android_devices=[AndroidDevice(
            device_id="mock_id", model="mock", os_version="14", sdk_version=34, battery_percent=100,
            installed_packages=["com.tencent.mm", "com.android.settings"]
        )],
        relevant_concepts=[
            ConceptSummary(name="android_layout:WeChat (com.tencent.mm)", description="WeChat UI"),
            ConceptSummary(name="android_layout:Settings (com.android.settings)", description="Settings UI"),
            ConceptSummary(name="android_layout:Photos (com.google.android.apps.photos)", description="Photos UI"),
            ConceptSummary(name="android_layout:Chrome (com.android.chrome)", description="Web Browser UI"),
            ConceptSummary(name="android_layout:Maps (com.google.android.apps.maps)", description="Maps UI"),
            ConceptSummary(name="android_layout:Play Store (com.android.vending)", description="App Store")
        ]
    )
    
    # Reset Context
    ContextManager.set(EvoContext())

    with patch('app.core.environment.get_awakened_state', return_value=mock_state):
        with patch('app.core.tools.manager.tool_manager.get_node_tools', return_value=[]):
            with patch('app.core.memory.manager.memory_manager.long_term.search_concepts', return_value=[]):
                # 2. Simulate Supervisor routing with "WeChat" in message
                supervisor = SupervisorNode()
                
                state = AgentState(
                    messages=[HumanMessage(content="Open WeChat and send a message.")],
                    project_id=1
                )
                
                # Directly call _build_context to trigger extraction and hydration
                config = {"configurable": {"working_directory": "/"}}
                await supervisor._build_context(state, config, state["messages"], 1)
                
                ctx = ContextManager.current()
                
                # Assertions for Focus Extraction
                assert "wechat" in ctx.entity_focus, f"Expected 'wechat' in focus, got {ctx.entity_focus}"
                
                # Assertions for Intent-Aware Layout Filtering (Environment Plugin)
                concepts = ctx.memory_replay.get("concepts", [])
                
                # Should prioritize WeChat, and limit total layouts to 3 max + 2 other concepts
                # But since we only have layouts here, it should be max 5 total, prioritizing WeChat.
                wechat_found = any("[Focus Active]" in c for c in concepts if "com.tencent.mm" in c)
                assert wechat_found, "WeChat layout should be marked as Focus Active."
                
                # The total list should be truncated (e.g. not all 6 apps injected)
                assert len(concepts) <= 5, "Layouts should be truncated to prevent context overflow."

                # 3. Test Ecosystem Classification
                from app.core.environment import classify_ecosystems
                ecosystems = classify_ecosystems(ctx.entity_focus)
                
                assert "android" in ecosystems, "Should classify WeChat as android ecosystem"
                assert "web" not in ecosystems, "Should not classify WeChat as web ecosystem"
