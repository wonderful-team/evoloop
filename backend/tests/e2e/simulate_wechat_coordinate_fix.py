import asyncio
import logging
from unittest.mock import AsyncMock, patch, MagicMock
from app.core.engine.nodes.dynamic_specialist import DynamicSpecialistNode
from tests.fixtures.factories import AgentStateFactory
from langchain_core.messages import AIMessage

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("skill_debug")

async def simulate_wechat_coordinate_issue():
    """
    Simulates the Agent trying to click WeChat search bar using the Vision-Guided SOP.
    This test demonstrates why raw coordinate clicking fails without offset.
    """
    worker = DynamicSpecialistNode()
    
    # Mocking the environment: WeChat at (500, 200)
    mock_app_info = {
        "name": "WeChat",
        "bounds": "500,200,800,600",
        "bundle_id": "com.tencent.xinWeChat"
    }

    print("\n--- 🕵️ Debugging WeChat Coordinate Flow ---")
    
    # Scenario: Agent takes a FOCUSED screenshot of WeChat
    # OCR returns "文件传输助手" at (100, 150) RELATIVE to the window
    relative_x, relative_y = 100, 150
    win_x, win_y = 500, 200
    expected_absolute_x = win_x + relative_x # 600
    expected_absolute_y = win_y + relative_y # 350

    print(f"Window Position: ({win_x}, {win_y})")
    print(f"Target (Relative to Window): ({relative_x}, {relative_y})")
    print(f"Expected Absolute Screen Click: ({expected_absolute_x}, {expected_absolute_y})")

    # 1. Simulating the "Failing" Case: Agent clicks raw coordinates from OCR
    with patch("app.infrastructure.drivers.macos.macos_driver.click") as mock_click:
        with patch("app.infrastructure.drivers.macos.macos_driver.get_current_app", return_value=mock_app_info):
            # If Agent forgets offset:
            print(f"\n❌ [Failure Simulation] Agent forgets offset and clicks ({relative_x}, {relative_y})")
            from app.domain.tools.environment.desktop import desktop_control
            await desktop_control.ainvoke({"action": "click", "x": relative_x, "y": relative_y})
            
            mock_click.assert_called_with(relative_x, relative_y)
            print(f"   Actual system click happened at ({relative_x}, {relative_y}) -> Likely clicked the Mac Menu Bar or Desktop!")

    # 2. Simulating the "Correct" Case via SOP Update (Manual Offset)
    with patch("app.infrastructure.drivers.macos.macos_driver.click") as mock_click:
        with patch("app.infrastructure.drivers.macos.macos_driver.get_current_app", return_value=mock_app_info):
            print(f"\n✅ [Success Simulation] Agent adds offset: ({win_x} + {relative_x}, {win_y} + {relative_y})")
            await desktop_control.ainvoke({"action": "click", "x": expected_absolute_x, "y": expected_absolute_y})
            
            mock_click.assert_called_with(expected_absolute_x, expected_absolute_y)
            print(f"   Actual system click happened at ({expected_absolute_x}, {expected_absolute_y}) -> Correct!")

    # 3. Simulating the "Shortcut" Case (New Recommended SOP)
    with patch("app.infrastructure.drivers.macos.macos_driver.key_press") as mock_key:
        print("\n🚀 [V5 Best Practice] Agent uses Cmd+F to search (No coordinates needed)")
        from app.domain.tools.environment.desktop import desktop_control
        await desktop_control.ainvoke({"action": "key_press", "key": "command+f"})
        
        mock_key.assert_called_with("command+f")
        print("   Shortcut triggered. Search focused reliably.")

    print("\n--- 🏁 Debugging Complete ---")

if __name__ == "__main__":
    asyncio.run(simulate_wechat_coordinate_issue())
