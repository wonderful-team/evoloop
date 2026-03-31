# 真实场景测试指南

## 🎯 测试场景

**场景描述**: 
> 打开 Chrome 查一下最新的 AI 新闻，把摘要存到剪贴板，然后打开微信发给其中的"文件传输助手"

这是一个典型的跨应用复杂任务，可以验证：
1. **键盘快捷键使用** - 是否使用 cmd+l 而不是点击地址栏
2. **Batch 模式** - 是否批量执行连续操作
3. **跨应用切换** - 是否高效切换 Chrome 和微信
4. **部分截图** - 是否使用区域截图提高效率

## 🚀 快速开始

### 1. 启动应用并准备环境

确保以下应用已启动：
- Google Chrome (已打开任意页面)
- WeChat (已登录并可见"文件传输助手")

### 2. 运行场景测试

```bash
cd /Users/huangjinhuan/项目/develop-assistant.cn/evoloop/backend

# 方法1: 使用实时测试脚本 (需要完整环境)
python tests/monitoring/test_real_scenario_ai_news.py --verbose --save /tmp/result.json

# 方法2: 使用生产环境 Agent
# 在 EvoLoop 应用中输入任务:
# "打开 Chrome 查一下最新的 AI 新闻，把摘要存到剪贴板，然后打开微信发给其中的'文件传输助手'"
```

### 3. 实时监控执行过程

```bash
# 获取线程 ID (从应用日志或数据库)
THREAD_ID="real-scenario-xxxxxx"

# 实时监控
python tests/monitoring/analyze_agent_execution.py --watch --thread-id $THREAD_ID
```

### 4. 查看分析报告

```bash
# 单次分析
python tests/monitoring/analyze_agent_execution.py --thread-id $THREAD_ID

# 或从日志文件分析
python tests/monitoring/analyze_agent_execution.py --file /path/to/execution_log.json
```

## 📊 预期优化表现

### 理想执行流程

```
Step 1: 分析请求
   → 获取当前环境

Step 2: 打开/切换到 Chrome
   → key_press(cmd+space)  # Spotlight
   → type_text("chrome")
   → key_press(return)

Step 3: 聚焦地址栏
   → screenshot(region)     # 部分截图
   → key_press(cmd+l)       # 快捷键而非点击

Step 4: 搜索 AI 新闻
   → batch:                 # Batch 模式！
     ├─ type_text("latest AI news")
     └─ key_press(return)

Step 5: 读取并复制摘要
   → screenshot(region)
   → click(article_title)   # 必要时才点击
   → key_press(cmd+a)       # 全选
   → key_press(cmd+c)       # 复制

Step 6: 切换到微信
   → key_press(cmd+tab)     # 切换应用
   → key_press(cmd+f)       # 搜索

Step 7: 发送消息
   → batch:                 # Batch 模式！
     ├─ type_text("文件传输助手")
     ├─ key_press(return)
     ├─ key_press(cmd+v)    # 粘贴
     └─ key_press(cmd+return) # 发送快捷键
```

### 优化指标预期

| 指标 | 优化前 (基线) | 优化后 (目标) | 提升 |
|-----|-------------|-------------|-----|
| 总耗时 | ~25-30s | ~12-15s | **50%** |
| 快捷键使用 | 20% | **85%** | +65% |
| Batch 使用 | 0次 | **2次** | +∞ |
| 截图次数 | 8-10次 | **2-3次** | -70% |
| 鼠标点击 | 15-20次 | **2-3次** | -85% |

## 🔍 验证检查清单

运行测试后，检查以下内容：

### ✅ 键盘快捷键检查
```bash
# 应该看到以下快捷键使用:
k logs -f evoloop-agent | grep "Converting click"
# 🚀 Converting click('发送') to shortcut 'cmd+return'
# 🚀 Converting click('地址栏') to shortcut 'cmd+l'
# 🚀 Converting click('关闭') to shortcut 'cmd+w'
```

### ✅ Batch 模式检查
```bash
k logs -f evoloop-agent | grep "action=batch"
# 应该看到 2 次 Batch 调用
```

### ✅ 部分截图检查
```bash
k logs -f evoloop-agent | grep "Auto-capturing window region"
# 应该看到使用 region 参数而非全屏
```

### ✅ OCR 坐标转换检查
```bash
k logs -f evoloop-agent | grep "Applying region offset"
# 确认坐标转换生效
```

## 📈 分析工具使用

### 评分标准

分析工具会给出 0-100 分的优化评分：

| 分数 | 评价 | 说明 |
|-----|-----|-----|
| 80-100 | 🌟 优秀 | Agent 很好地使用了速度优化 |
| 60-79 | ✅ 良好 | 基本使用优化，仍有改进空间 |
| 40-59 | ⚠️ 一般 | 部分使用优化，需要调优 |
| <40 | ❌ 需改进 | 优化未生效，检查配置 |

### 评分维度

1. **快捷键使用 (40分)**
   - 80%+ 使用率: +40分
   - 50%+ 使用率: +25分
   - 有使用: +10分
   - 未使用: 0分

2. **Batch 模式 (30分)**
   - 2+ 次使用: +30分
   - 1 次使用: +15分
   - 未使用: 0分

3. **键盘优先 (30分)**
   - 70%+ 键盘比例: +30分
   - 50%+ 键盘比例: +20分
   - 30%+ 键盘比例: +10分
   - <30%: 0分

## 🔧 故障排查

### 问题1: 快捷键未生效

**现象**: Agent 仍然使用 click 而非 key_press

**检查**:
1. 确认 `app/core/shortcuts.py` 已加载
2. 检查应用 bundle_id 是否在数据库中
3. 查看日志是否有 "Converting click" 消息

**解决**:
```python
# 在 desktop_controller.py 中添加调试日志
logger.info(f"🚀 Converting click('{element_name}') to shortcut '{shortcut}'")
```

### 问题2: Batch 未使用

**现象**: Agent 逐个执行操作而非 batch

**检查**:
1. 确认工具描述中包含 Batch 指南
2. 查看提示词是否强调批量执行

**解决**:
```python
# 在提示词中添加强调
desktop_control 的 description 中必须包含:
"USE BATCH MODE for continuous operations in same field"
```

### 问题3: 坐标偏移

**现象**: 部分截图时点击位置错误

**检查**:
1. 确认 `region` 参数正确传递
2. 检查 OCR 坐标转换逻辑

**解决**:
```python
# 确认坐标转换公式
screen_x = ocr_x + region_offset_x
screen_y = ocr_y + region_offset_y
```

## 📊 报告示例

```
================================================================================
🎯 Agent 执行过程分析报告
================================================================================

场景: 打开 Chrome 查一下最新的 AI 新闻...
总步骤数: 7
总耗时: 11.7s

📊 工具调用统计:
  总工具调用: 14 次
  ├─ 截图: 2 次
  ├─ 键盘按键: 7 次
  ├─ 鼠标点击: 1 次
  └─ Batch: 2 次

🚀 优化效果分析:
  快捷键使用: 6 次 (85.7% 使用率)
  快捷键列表: ['cmd+a', 'cmd+tab', 'cmd+space', 'cmd+c', 'cmd+f', 'cmd+l']
  键盘/鼠标比例: 87.5%

📈 优化评分:
  ✅ 快捷键使用优秀: +40分
  ✅ Batch 使用优秀: +30分
  ✅ 键盘优先: +30分

  总分: 100/100
  🌟 优秀! Agent 很好地使用了速度优化
```

## 📝 后续优化建议

1. **扩展快捷键数据库**: 根据实际使用场景添加更多应用快捷键
2. **智能 Batch 检测**: 自动识别可批量的操作序列
3. **失败重试策略**: 快捷键失败时自动回退到点击
4. **用户反馈闭环**: 收集实际使用数据持续优化
