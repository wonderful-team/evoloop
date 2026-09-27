"""
Desktop Control Tool — Agent-facing thin wrapper over DesktopController.

This module exposes `desktop`
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
