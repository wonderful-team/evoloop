# 新动作测试规范与验证指南

## 概述

本文档定义了需要添加到三个环境控制工具中的新动作的具体测试场景、期望行为和验证方法。

---

## 1. Browser Control 新增动作

### 1.1 `batch` - 批量操作

**动机**：减少 LLM 调用次数，提高复杂工作流效率

**API 设计**：
```python
async def browser_control(
    action: "batch",
    actions: list[dict],           # 动作列表
    continue_on_error: bool = True, # 出错是否继续
    delay_ms: int = 100,           # 动作间延迟
)
```

**测试场景 1：GitHub 搜索工作流**
```python
{
    "action": "batch",
    "actions": [
        {"action": "navigate", "url": "https://github.com"},
        {"action": "click", "selector": "[name='q']"},
        {"action": "type_text", "selector": "[name='q']", "value": "python asyncio"},
        {"action": "key_press", "key": "Enter"},
        {"action": "wait_for", "selector": ".repo-list", "timeout_ms": 10000}
    ],
    "continue_on_error": False,
    "delay_ms": 500
}
```

**期望结果**：
- 执行完所有步骤后，页面显示搜索结果
- 返回包含每步执行状态和耗时的报告
- 格式示例：
```
✅ Batch Complete: 5/5 succeeded (8.2s)
  ✅ Step 1: navigate (1200ms)
  ✅ Step 2: click (350ms)
  ✅ Step 3: type_text (280ms)
  ✅ Step 4: key_press (150ms)
  ✅ Step 5: wait_for (3200ms)
```

**测试场景 2：表单填写工作流**
```python
{
    "action": "batch",
    "actions": [
        {"action": "navigate", "url": "https://httpbin.org/forms/post"},
        {"action": "type_text", "selector": "[name='custname']", "value": "Test User"},
        {"action": "type_text", "selector": "[name='custtel']", "value": "13800138000"},
        {"action": "select_option", "selector": "[name='size']", "value": "large"},
        {"action": "click", "selector": "[value='Submit']"}
    ]
}
```

---

### 1.2 `upload` - 文件上传

**动机**：支持文件上传自动化场景

**API 设计**：
```python
async def browser_control(
    action: "upload",
    selector: str | None = None,    # 文件输入元素选择器
    text: str | None = None,        # 文本定位替代
    file_path: str,                 # 本地文件路径（必需）
    timeout_ms: int = 10000,
)
```

**测试场景 1：单文件上传**
```python
# 使用 https://the-internet.herokuapp.com/upload
{
    "action": "upload",
    "selector": "#file-upload",
    "file_path": "/tmp/test_upload.txt"
}
# 后续需要手动点击上传按钮或配置自动提交
```

**测试场景 2：拖放上传区域**
```python
# 某些网站支持拖放上传
test_file = "/tmp/test_image.png"
{
    "action": "upload",
    "selector": ".dropzone",  # 拖放区域
    "file_path": test_file
}
```

**验证步骤**：
1. 创建临时测试文件
2. 访问上传测试页面
3. 执行 upload 动作
4. 验证文件名出现在页面上或提交成功

---

## 2. Desktop Control 新增动作

### 2.1 `scroll` - 滚动操作

**动机**：Desktop 缺少滚动长页面的能力

**API 设计**：
```python
async def desktop_control(
    action: "scroll",
    direction: Literal["up", "down", "left", "right"],  # 方向
    amount: int = 300,                                   # 滚动量（像素）
    element_name: str | None = None,                    # 特定元素内滚动
    x: int | None = None,                               # 鼠标位置 X
    y: int | None = None,                               # 鼠标位置 Y
)
```

**测试场景 1：Safari 网页滚动**
```python
# 前置：打开 Safari 并访问长页面
await desktop_control(action="open_app", app_name="Safari")
# 使用 AppleScript 导航到 news.ycombinator.com

# 向下滚动
{
    "action": "scroll",
    "direction": "down",
    "amount": 500
}

# 截图对比验证
```

**测试场景 2：特定元素内滚动**
```python
# 在 Finder 的列表视图中滚动
{
    "action": "scroll",
    "direction": "down",
    "amount": 300,
    "element_name": "文件列表"  # 或使用 element_role
}
```

**实现思路**：
```python
# 方法1: 使用 AppleScript 触发滚动事件
script = f'''
tell application "System Events"
    key code 121  # Page Down
    -- 或
    scroll {amount} of application process "Safari"
end tell
'''

# 方法2: 使用 Quartz 直接发送滚动事件
from Quartz import (
    CGEventCreateScrollWheelEvent,
    CGEventPost,
    kCGHIDEventTap,
)
event = CGEventCreateScrollWheelEvent(None, kCGScrollEventUnitPixel, 2, -amount, 0)
CGEventPost(kCGHIDEventTap, event)

# 方法3: 鼠标移动到位置后滚动
# 结合 element_name 解析获取坐标
```

---

### 2.2 `drag_drop` - 拖拽操作

**动机**：支持文件管理、排序等场景

**API 设计**：
```python
async def desktop_control(
    action: "drag_drop",
    # 方式1: 元素名称
    source_element: str | None = None,
    target_element: str | None = None,
    # 方式2: 坐标
    x: int | None = None,
    y: int | None = None,
    x2: int | None = None,
    y2: int | None = None,
    duration_ms: int = 500,  # 拖拽持续时间
)
```

**测试场景 1：Finder 中拖拽文件**
```python
# 在 Finder 中将文件从一个文件夹拖到另一个
{
    "action": "drag_drop",
    "source_element": "test_file.txt",
    "target_element": "目标文件夹"
}
```

**测试场景 2：桌面图标重新排列**
```python
{
    "action": "drag_drop",
    "x": 100, "y": 200,     # 源坐标
    "x2": 500, "y2": 400    # 目标坐标
}
```

**实现思路**：
```python
# 使用 Quartz 实现拖拽
from Quartz import (
    CGEventCreateMouseEvent,
    CGEventPost,
    CGPointMake,
    kCGEventLeftMouseDown,
    kCGEventLeftMouseUp,
    kCGEventLeftMouseDragged,
    kCGHIDEventTap,
)

point1 = CGPointMake(x, y)
point2 = CGPointMake(x2, y2)

# Mouse down
event_down = CGEventCreateMouseEvent(None, kCGEventLeftMouseDown, point1, 0)
CGEventPost(kCGHIDEventTap, event_down)

# Drag events with interpolation for smooth movement
steps = 10
for i in range(steps):
    interp_x = x + (x2 - x) * i / steps
    interp_y = y + (y2 - y) * i / steps
    point = CGPointMake(interp_x, interp_y)
    event_drag = CGEventCreateMouseEvent(None, kCGEventLeftMouseDragged, point, 0)
    CGEventPost(kCGHIDEventTap, event_drag)
    time.sleep(duration_ms / 1000 / steps)

# Mouse up
event_up = CGEventCreateMouseEvent(None, kCGEventLeftMouseUp, point2, 0)
CGEventPost(kCGHIDEventTap, event_up)
```

---

## 3. Mobile Control 新增动作

### 3.1 `scroll` - 语义化滚动

**动机**：提供比 `swipe` 更符合 LLM 思维的语义化滚动操作

**API 设计**：
```python
async def mobile_control(
    action: "scroll",
    direction: Literal["up", "down", "left", "right"],
    element_name: str | None = None,  # 在特定元素/区域内滚动
    amount: Literal["small", "medium", "large", "full"] = "medium",
    # 或具体数值
    distance: int | None = None,  # 像素值，内部转换为坐标
)
```

**测试场景 1：列表向下滚动**
```python
# 在知乎/微博等 Feed 流中向下滚动
{
    "action": "scroll",
    "direction": "down",
    "amount": "medium"  # 相当于屏幕高度的 50%
}
# 内部转换为：从屏幕下方 70% 处滑动到 30% 处
```

**测试场景 2：在特定卡片内滚动**
```python
{
    "action": "scroll",
    "direction": "down",
    "element_name": "评论列表",
    "amount": "small"
}
```

**与现有 `swipe` 的关系**：
- `scroll`: 语义化、高层级，面向业务场景
- `swipe`: 底层坐标操作，精确控制

**实现映射**：
```python
AMOUNT_MAP = {
    "small": 0.3,    # 30% 屏幕高度
    "medium": 0.5,   # 50% 屏幕高度
    "large": 0.7,    # 70% 屏幕高度
    "full": 0.9,     # 90% 屏幕高度
}

async def scroll(...):
    screen_w, screen_h = await get_screen_size()
    ratio = AMOUNT_MAP.get(amount, 0.5)

    # 向下滚动 = 从下往上滑动
    start_y = int(screen_h * 0.7)
    end_y = int(screen_h * (0.7 - ratio))
    center_x = int(screen_w * 0.5)

    if element_name:
        # 解析元素，在元素中心区域滚动
        resolved = await resolve_element(element_name)
        center_x = resolved["x"]
        start_y = resolved["y"] + int(resolved.get("height", screen_h) * 0.3)
        end_y = resolved["y"] - int(resolved.get("height", screen_h) * 0.3)

    return await swipe(center_x, start_y, center_x, end_y)
```

---

## 4. 测试验证清单

### 4.1 Browser `batch`

- [ ] 5个动作的序列可以连续执行
- [ ] `continue_on_error=False` 时，出错立即停止
- [ ] `continue_on_error=True` 时，出错记录并继续
- [ ] 返回结果包含每步的耗时和状态
- [ ] 延迟参数正确生效
- [ ] 嵌套的 element_name 解析正常工作

### 4.2 Browser `upload`

- [ ] 可以上传本地存在的文件
- [ ] 文件选择器可以正确定位（selector/text）
- [ ] 上传后文件名正确显示
- [ ] 文件不存在时返回清晰的错误

### 4.3 Desktop `scroll`

- [ ] 四个方向滚动都有效
- [ ] 不同滚动量（amount）产生不同效果
- [ ] 在 Safari/Chrome 中滚动网页有效
- [ ] 在 Finder 中滚动列表有效
- [ ] 指定 element_name 时在元素内滚动

### 4.4 Desktop `drag_drop`

- [ ] 坐标方式拖拽有效
- [ ] 元素名称方式拖拽有效
- [ ] 拖拽过程平滑（有中间点）
- [ ] 目标位置正确
- [ ] Finder 中文件可以拖放

### 4.5 Mobile `scroll`

- [ ] 四个方向滚动都有效
- [ ] 不同 amount 映射到不同的滑动距离
- [ ] 在 Feed 流中向下滚动加载更多内容
- [ ] 在设置列表中滚动查找选项
- [ ] 与现有 swipe 结果一致（只是 API 更友好）

---

## 5. 执行测试

```bash
# 1. 运行所有测试
python test_new_actions.py --all

# 2. 运行单个测试
python test_new_actions.py --test browser_batch
python test_new_actions.py --test browser_upload
python test_new_actions.py --test desktop_scroll
python test_new_actions.py --test desktop_drag_drop
python test_new_actions.py --test mobile_scroll
```

**预期输出示例**：
```
======================================================================
🚀 RUNNING ALL NEW ACTION VALIDATION TESTS
======================================================================

🧪 Testing browser_control batch action...
============================================================
1. Navigate: ✅ Navigated to: https://github.com...

2. Executing batch actions (simulated):
   Step 1: click
   Step 2: type_text
   Step 3: key_press
   Step 4: wait_for

3. Final state: URL: https://github.com/search?q=python+asyncio...

✅ PASS | browser_batch | 8200ms | Batch sequence executed successfully

...

======================================================================
📊 TEST RESULTS SUMMARY
======================================================================
✅ PASS | browser_batch | 8200ms | Batch sequence executed successfully
✅ PASS | browser_upload | 4500ms | File upload workflow completed
✅ PASS | desktop_scroll | 6200ms | Scroll action simulated (Page Down)
⚠️ SKIP | desktop_drag_drop | 1200ms | Drag-drop setup validated (needs implementation)
✅ PASS | mobile_scroll | 3800ms | Scroll simulated via swipe
----------------------------------------------------------------------
Total: 5 | ✅ Passed: 4 | ⚠️ Skipped: 1
======================================================================
```

---

## 6. 实施建议优先级

| 优先级 | 动作 | 理由 |
|--------|------|------|
| P0 | Browser `batch` | 最影响 LLM 效率，减少 API 调用次数 |
| P0 | Desktop `scroll` | 基础功能缺失，影响网页/文档操作 |
| P1 | Browser `upload` | 特定场景必需（上传截图、文件等） |
| P1 | Mobile `scroll` | API 友好性改进，现有 swipe 可 workaround |
| P2 | Desktop `drag_drop` | 使用频率较低，可用 click+key_press 替代 |
