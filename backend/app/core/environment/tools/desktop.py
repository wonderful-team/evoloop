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
    """
    控制 macOS 桌面——速度优化版

    速度优先规则——遵守这些能快 3 倍：

    规则 1：键盘优先（始终优先键盘而非鼠标）
      - 好：key_press("cmd+w") 关窗口
      - 好：key_press("return") 发消息
      - 好：key_press("cmd+v") 粘贴
      - 坏：不要点坐标，除非键盘做不到

    规则 2：用批量模式（多个动作一起执行）
      - 好：当所有步骤都在**同一个输入框**时
      - 好：示例：[点击输入框 -> 输入 -> 回车] 作为一个 batch
      - 好：步骤间跳过验证，最后再验证
      - 坏：不要跨不同屏幕或加载状态批量

    规则 3：跳过不必要的截图
      - 好：批量中只在开始和结束时截图
      - 坏：不要每个动作后都截图

    常用快捷键（记牢这些！）
    - 微信：return（发送）、cmd+f（搜索）、cmd+n（新会话）
    - Chrome：cmd+l（地址栏）、cmd+t（新标签）、cmd+w（关标签）
    - 系统：cmd+tab（切换 App）、cmd+space（Spotlight）

    示例

    快 - 发微信消息（1 个 batch 里 3 个动作）：
      desktop(action="batch", actions=[
          {"action": "click", "element_name": "输入框"},
          {"action": "type_text", "text": "Hello"},
          {"action": "key_press", "key": "return"}
      ])

    慢 - 不要这样做（3 次单独调用 + 截图）：
      desktop(action="click") -> screenshot -> verify
      desktop(action="type_text") -> screenshot -> verify
      desktop(action="key_press") -> screenshot -> verify

    Args:
        action: 要执行的动作：
            - "screenshot": 截取屏幕。返回图片文件路径。
            - "click": 在坐标 (x, y) 或按 element_name 点击。
            - "double_click": 在坐标 (x, y) 或按 element_name 双击。
            - "type_text": 输入给定文本。
            - "key_press": 按特殊键（enter、escape、tab 等）。
            - "open_app": 按名称打开或聚焦应用。
            - "applescript": 执行原始 AppleScript。**警告**：不要对动态 App（微信、Chrome、
              Electron 应用）用此动作——它们缺少健壮的 AppleScript 支持。用原生 type_text/click。
            - "get_info": 获取系统硬件与 OS 环境信息。
            - "list_apps": 列出 /Applications 中已安装应用。
            - "get_active_app": 获取当前聚焦应用的名称、标题与窗口 bounds。
            - "scroll": 按给定方向滚动 amount 像素。
            - "drag_drop": 从源拖到目标（按元素名或坐标）。
            - "dump_ui": 把 Accessibility Tree dump 成 JSON 数组（UI 元素）。
            - "gui_extract": 用 OCR 从区域或坐标 (x, y) 附近智能提取文本。
            - "batch": 按顺序执行多个动作。用于多步工作流，如：点输入框 -> 输入 -> 回车。
              见 'actions' 参数。
        x: click 动作的 X 坐标。
        y: click 动作的 Y 坐标。
        element_name: 要点击的 UI 元素语义名/标签（如 "Login"、"Close"）。
        target: element_name 的别名（跨工具一致性）。
        element_role: 元素的可选角色过滤（如 "AXButton"、"AXTextField"）。
        text: type_text 动作要输入的文本。
        key: key_press 动作的键名或组合（如 "enter"、"tab"、"a"、"command+a"、"shift+tab"）。
        app_name: open_app 动作的应用名（如 "Safari"、"Terminal"）。
        script: applescript 动作的 AppleScript 代码。
        region: screenshot 动作的可选区域 "x,y,w,h"。
            不提供时取决于 ENABLE_PARTIAL_SCREENSHOT 配置：
            - True（默认）：自动截当前活动窗口区域
            - False：截全屏
            无法确定窗口 bounds 时回退到全屏。
            示例：
            - 自动截当前窗口：region=None（大多数情况推荐）
            - 截指定区域：region="500,300,200,100"（来自 OCR/元素 bounds）
            - 截指定窗口：region="624,102,1195,812"（来自 get_active_app）
        force_keystroke: type_text 为 True 时用慢速 AppleScript keystroke 而非快速剪贴板粘贴。
        ocr: "screenshot" 为 True 时立即跑 OCR 并返回文本元素 + 坐标。
            注意：坐标会自动转成屏幕坐标（即使局部截图）。可直接用于 click/double_click。
        actions: batch 模式的动作 dict 列表。

            正确用例（适合批量）：
            - 所有动作都针对**同一个输入框**
            - 纯键盘序列：[cmd+f -> 输入 -> 回车]
            - 已知工作流：[点输入框 -> 输入 -> 回车发送]

            不要用批量（用单独调用 + 验证）：
            - 会改变屏幕/状态的动作
            - 需要等待加载的动作
            - 跨不同窗口的动作

            示例 1 - 微信发消息（好）：
            [
                {"action": "click", "element_name": "输入框"},
                {"action": "type_text", "text": "Hello"},
                {"action": "key_press", "key": "return"}
            ]
            结果：开始 1 张截图、结束 1 张。快！

            示例 2 - Chrome 搜索（好）：
            [
                {"action": "key_press", "key": "cmd+l"},      # 聚焦地址栏
                {"action": "key_press", "key": "cmd+a"},      # 全选
                {"action": "type_text", "text": "google.com"},
                {"action": "key_press", "key": "return"}
            ]
            结果：全是键盘，非常快，无需坐标！

            示例 3 - 填表单（好）：
            [
                {"action": "click", "element_name": "用户名"},
                {"action": "type_text", "text": "user@example.com"},
                {"action": "key_press", "key": "tab"},        # 下一字段
                {"action": "type_text", "text": "password"},
                {"action": "key_press", "key": "return"}      # 提交
            ]
            结果：5 个动作，1 个 batch，共 2 张截图
        continue_on_error: batch 模式是否出错继续（默认 True）。
        delay_ms: batch 模式动作间延迟毫秒（默认 100）。
        direction: scroll 动作的滚动方向（up/down/left/right）。
        amount: 滚动像素（默认 300）。
        x2, y2: drag_drop 动作的目标坐标。
        source_element: drag_drop 的源元素名（x, y 的替代）。
        target_element: drag_drop 的目标元素名（x2, y2 的替代）。
        duration_ms: 拖拽操作时长毫秒（默认 500）。
        role_filter: dump_ui 时按角色过滤元素（如 'AXButton'）。
        name_filter: dump_ui 时按名称过滤元素（部分匹配）。
        max_depth: dump_ui 的最大遍历深度（默认 10）。
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
    用 AX Tree 快速检查屏幕状态（无 LLM，~500ms 对比 analyze_image 的 ~12s）。

    简单的检查用本工具而非 analyze_image，如：
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
        快速检查结果（比 analyze_image 快得多）
    """
    return await DesktopController.quick_check_screen(**locals())
