"""
Desktop Control Tool — Agent-facing thin wrapper over DesktopController.

This module exposes `desktop`, `verify_ui_state`, `quick_check_screen`
as @evoloop_tools so the Agent can call them via function calling.
All actual logic lives in:
  app.core.environment.controllers.desktop.DesktopController
"""

import logging
from typing import Literal

from app.core.environment.controllers.desktop import DesktopController
from app.core.tools import evoloop_tool

logger = logging.getLogger(__name__)


@evoloop_tool(
    required_benefit="desktop",
    summary_template="evoloop.tool_summary.desktop",
)
async def desktop(
    action: Literal[
        "screenshot",
        "click",
        "double_click",
        "type_text",
        "key_press",
        "open_app",
        "applescript",
        "get_info",
        "list_apps",
        "batch",
        "get_active_app",
        "scroll",
        "drag_drop",
        "dump_ui",
        "gui_extract",
    ] = "screenshot",
    x: int | None = None,
    y: int | None = None,
    element_name: str | None = None,
    target: str | None = None,  # Alias for element_name (cross-tool consistency)
    element_role: str | None = None,
    text: str | None = None,
    key: str | None = None,
    app_name: str | None = None,
    script: str | None = None,
    region: str | None = None,
    force_keystroke: bool = False,
    ocr: bool = False,
    actions: list[dict] | None = None,
    continue_on_error: bool = True,
    delay_ms: int = 300,
    # Scroll params
    direction: Literal["up", "down", "left", "right"] | None = None,
    amount: int = 300,
    # Drag drop params
    x2: int | None = None,
    y2: int | None = None,
    source_element: str | None = None,
    target_element: str | None = None,
    duration_ms: int = 500,
    # Dump UI params
    role_filter: str | None = None,
    name_filter: str | None = None,
    max_depth: int = 10,
) -> str:
    """控制 macOS 桌面——截图/点击/输入/按键/批量/AX 树。

    速度纪律（快 3 倍的关键）：优先 key_press 而非点坐标；把稳定的多步动作合进一个
    batch（只限同屏/纯键盘/不改状态的动作）；截图只在开始/结束各一次，不要每步都截。
    定位顺序：element_name（AX 语义名）> screenshot(ocr=True) 返回的文本+屏幕坐标（可
    直接回填 click）> 裸坐标；看不清界面先 dump_ui。
    applescript 动作不要用于动态 App（微信/Chrome/Electron）——用原生 click/type_text/key_press。
    完整操作规程（快捷键表/batch 范例/region 局部截图语义/逐参数说明）加载
    skill(name="Desktop Automation SOP")。
    """
    # Parameter alias: target -> element_name (cross-tool consistency)
    if target and not element_name:
        element_name = target
    return await DesktopController.execute(**locals())


@evoloop_tool(summary_template="evoloop.tool_summary.verify_ui_state")
async def verify_ui_state(
    expected_element: str | None = None,
    expected_role: str | None = None,
    expected_text: str | None = None,
    timeout_seconds: int = 5,
) -> str:
    """
    用 AX Tree 验证屏幕上是否存在某个 UI 元素或文本。
    在 'click' 或 'type_text' 后用本工具确保 UI 按预期响应。

    Args:
        expected_element: 要查找的 UI 元素的部分名称。
        expected_role: 元素的可选角色（如 'AXWindow'、'AXButton'）。
        expected_text: 应出现在树中任意位置的可选文本。
        timeout_seconds: （当前未实现轮询，只做一次立即检查）。
    """
    return await DesktopController.verify_ui_state(**locals())


@evoloop_tool(summary_template="evoloop.tool_summary.quick_check_screen")
async def quick_check_screen(
    check_type: Literal["has_text", "has_element", "is_loaded"] = "is_loaded",
    target: str | None = None,
    timeout_seconds: int = 5,
) -> str:
    """
    用 AX Tree 快速检查屏幕状态（无 LLM，~500ms 对比 image(analyze) 的 ~12s）。

    简单的检查用本工具而非 image(analyze)，如：
    - "页面加载了吗？" -> quick_check_screen("is_loaded")
    - "显示了 'AI news' 吗？" -> quick_check_screen("has_text", "AI news")
    - "有 Search 按钮吗？" -> quick_check_screen("has_element", "Search")

    Args:
        check_type: 要检查什么：
            - "has_text": 检查目标文本是否出现在屏幕上任意位置
            - "has_element": 检查是否存在名为 target 的元素
            - "is_loaded": 检查 UI 是否已稳定（元素已出现、无加载指示器）
        target: 要搜索的文本或元素名（用于 has_text/has_element）
        timeout_seconds: 轮询超时（每 500ms 检查一次直到超时）

    Returns:
        快速检查结果（比 image(analyze) 快得多）
    """
    return await DesktopController.quick_check_screen(**locals())
