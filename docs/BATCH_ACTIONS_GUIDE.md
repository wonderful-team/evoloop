# macOS Batch 多步操作指南

## 概述

Batch 功能允许在一次调用中执行多个桌面操作，无需中间截图验证。适合确定性的、连续的操作流程。

## 传统方式 vs Batch 方式

### 传统方式（逐步验证）

```
AI: 发送微信消息给用户

1. screenshot + OCR → 找到聊天列表
2. click("文件传输助手")  
3. screenshot + OCR → 确认进入聊天窗口
4. click("输入框")
5. screenshot + OCR → 确认输入框聚焦
6. type_text("Hello World")
7. screenshot + OCR → 确认文本已输入
8. click("发送按钮")
9. screenshot → 确认发送成功

总计: 5 次截图, 4 次 OCR, 9 次 API 调用
```

### Batch 方式（多步操作）

```
AI: 发送微信消息给用户

1. screenshot + OCR → 找到聊天列表
2. batch([
     {"action": "click", "element_name": "文件传输助手"},
     {"action": "click", "element_name": "输入框"},
     {"action": "type_text", "text": "Hello World"},
     {"action": "key_press", "key": "return"}
   ])
3. screenshot → 确认发送成功

总计: 2 次截图, 1 次 OCR, 3 次 API 调用
```

### 效果对比

| 指标 | 传统方式 | Batch 方式 | 节省 |
|------|---------|-----------|------|
| 截图次数 | 5 | 2 | 60% |
| OCR 次数 | 4 | 1 | 75% |
| API 调用 | 9 | 3 | 67% |
| 执行时间 | ~15s | ~5s | 67% |

## 使用方法

### API 调用

```python
desktop_control(
    action="batch",
    actions=[
        # 步骤 1: 点击输入框
        {"action": "click", "element_name": "输入框"},
        
        # 步骤 2: 输入文本
        {"action": "type_text", "text": "Hello World"},
        
        # 步骤 3: 回车发送
        {"action": "key_press", "key": "return"}
    ],
    continue_on_error=True,  # 出错是否继续
    delay_ms=300             # 步骤间延迟（毫秒）
)
```

### 支持的 Action

| Action | 参数 | 说明 |
|--------|------|------|
| `click` | `x`, `y` 或 `element_name` | 点击坐标或元素 |
| `double_click` | `x`, `y` 或 `element_name` | 双击 |
| `type_text` | `text`, `force_keystroke` | 输入文本 |
| `key_press` | `key` | 按键（enter, tab, escape 等）|
| `scroll` | `direction`, `amount` | 滚动 |
| `screenshot` | `region`, `ocr` | 截图 |

## 使用场景

### ✅ 适合使用 Batch 的场景

1. **表单填写**
   ```python
   actions=[
       {"action": "click", "element_name": "用户名"},
       {"action": "type_text", "text": "user@example.com"},
       {"action": "key_press", "key": "tab"},
       {"action": "type_text", "text": "password123"},
       {"action": "key_press", "key": "return"}
   ]
   ```

2. **消息发送**
   ```python
   actions=[
       {"action": "click", "element_name": "输入框"},
       {"action": "type_text", "text": "消息内容"},
       {"action": "key_press", "key": "return"}
   ]
   ```

3. **菜单导航**
   ```python
   actions=[
       {"action": "click", "element_name": "文件"},
       {"action": "click", "element_name": "打开"},
       {"action": "type_text", "text": "~/Documents"},
       {"action": "key_press", "key": "return"}
   ]
   ```

### ❌ 不适合使用 Batch 的场景

1. **需要动态判断的操作**
   - 需要等待某个元素出现
   - 需要根据界面状态做决策

2. **可能失败的操作**
   - 元素位置不确定
   - 网络请求等待

3. **需要人工确认的操作**
   - 涉及删除、支付等敏感操作

## 最佳实践

### 1. 错误处理

```python
desktop_control(
    action="batch",
    actions=[...],
    continue_on_error=False  # 出错立即停止，方便调试
)
```

### 2. 延迟设置

```python
desktop_control(
    action="batch",
    actions=[...],
    delay_ms=500  # 较慢的应用需要更长延迟
)
```

### 3. 混合策略

```python
# 对于不确定的操作，使用传统方式
screenshot(ocr=True)  # 确认当前状态

# 对于确定的操作链，使用 batch
batch([
    {"action": "click", "element_name": "确定"},
    {"action": "type_text", "text": "..."},
    {"action": "key_press", "key": "return"}
])

# 再次确认结果
screenshot(ocr=True)
```

## 实现原理

### Backend 代码

```python
# backend/app/core/environment/controllers/desktop_controller.py

elif action == "batch":
    if not actions:
        return "Error: 'actions' list is required for batch action."
    
    batch_start = time.time()
    executor = BatchExecutor(continue_on_error=continue_on_error, delay_ms=delay_ms)
    
    async def _exec_action(action_dict: dict) -> str:
        params = {k: v for k, v in action_dict.items() if k != "action" and v is not None}
        return await cls.execute(action=action_dict.get("action", "unknown"), **params)
    
    await executor.execute(actions, _exec_action)
    return executor.format_summary(time.time() - batch_start)
```

### 执行流程

```
User Request
    ↓
AI Planning
    ↓
desktop_control(action="batch", actions=[...])
    ↓
BatchExecutor.execute()
    ├── action 1: click()
    ├── delay_ms
    ├── action 2: type_text()
    ├── delay_ms
    └── action 3: key_press()
    ↓
Return Summary
```

## 配置说明

在 `.env` 文件中可以配置默认延迟：

```bash
# Batch 操作默认延迟（毫秒）
BATCH_DEFAULT_DELAY_MS=300
```

## 故障排除

### 问题：Batch 执行失败

**可能原因：**
1. 元素在操作间状态变化
2. 延迟不够，应用响应慢
3. 元素位置计算错误

**解决方案：**
1. 增加 `delay_ms`
2. 拆分为多个 batch
3. 使用 `continue_on_error=False` 定位问题步骤

### 问题：坐标不准确

**可能原因：**
1. 使用了局部截图 + OCR 但没有转换坐标
2. 窗口移动导致坐标变化

**解决方案：**
1. 确保使用 `element_name` 而不是硬编码坐标
2. 每次 batch 前重新获取元素位置

## 示例代码

### 完整示例：微信发送消息

```python
# 1. 找到聊天窗口
result = desktop_control(action="screenshot", ocr=True)
# OCR 返回: 文件传输助手 at (1000, 200)

# 2. 点击进入并发送消息
desktop_control(
    action="batch",
    actions=[
        {"action": "click", "x": 1000, "y": 200},
        {"action": "click", "element_name": "输入框"},
        {"action": "type_text", "text": "Hello from EvoLoop!"},
        {"action": "key_press", "key": "return"}
    ],
    delay_ms=500
)

# 3. 确认发送成功
result = desktop_control(action="screenshot", ocr=True)
```

## 总结

Batch 操作是提高自动化效率的关键功能：

- ✅ 减少 60-70% 的截图和 OCR 调用
- ✅ 减少 Token 消耗和 API 费用
- ✅ 提高执行速度
- ✅ 代码更简洁

**核心原则：**
- 确定性操作 → 使用 Batch
- 不确定性操作 → 使用传统方式（逐步验证）
