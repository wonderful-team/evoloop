# L0 Intent Classifier — 本地 BERT 通用指令理解引擎

## 1. 设计目标

### 1.1 核心目标
将当前 L0 层从规则穷举（`local_matcher.py`）升级为基于 BERT 的通用指令理解引擎。不再限定 17 种系统动作——**所有 macro、未来新增的指令、以及任何用户可能口语化表达的意图**，都通过同一分类器识别。分类器高置信时本地毫秒级执行，低置信时无缝 fallback LLM Agent 兜底。新指令只需写示例 → 重训 → 热生效，不改代码。

### 1.2 关键指标

| 指标 | 目标 | 当前（正则 L0） |
|------|------|----------------|
| 延迟 | <= 20ms（本地 ANE 推理） | < 1ms |
| 意图识别准确率 | >= 95%（top-1 match @ threshold 0.85） | 精确匹配时 100%，不匹配时 0% |
| 口语变化适应性 | "帮我把那个音量调大一点" 自动泛化 | 必须穷举每一句话 |
| 覆盖范围 | 所有 macro + 内置指令（不限数量） | 50+ 模板，需人工逐条写 |
| 离线能力 | 完全本地，不依赖外网 | ✅ 已满足 |
| 热更新 | 修改意图示例后重新训练 <= 3 分钟，热加载模型 | 改数据库即刻生效 |
| 最低置信度阈值 | 0.85（低于此值 fallback LLM Agent） | 无 |

### 1.3 架构定位

```
ASR text
  → L0 通用分类器（BERT + Core ML / ONNX）
    → confidence >= 0.85 → 执行 macro / builtin（本地毫秒级）
    → confidence < 0.85  → fallback LLM Agent（云端 ~2s / 本地 ~500ms）
```

与旧 L0 的关键区别：

| 维度 | 旧 L0（规则穷举） | 新 L0（BERT 分类器） |
|------|-----------------|-------------------|
| 覆盖范围 | 50+ 模板，手动维护 | 所有 macro + 内置指令，示例驱动 |
| 新增指令 | 改代码或数据库 + 重启 | 写 YAML 示例 → 重训 3min → 热加载 |
| 泛化能力 | 精确字面匹配，变体全写才认 | BERT 语义泛化，变体自动覆盖 |
| 处理极限意图 | 不影响 | 低置信 → fallback LLM，不误执行 |
| 延迟 | < 1ms | 5-15ms（ANE）|

---

## 2. 技术选型

| 层 | 选择 | 理由 |
|----|------|------|
| 基座模型 | `bert-base-chinese` | 中文预训练，12 层 Transformer，110M 参数 |
| 训练框架 | HuggingFace `transformers` + `datasets` | 工业标准，训练脚本 50 行 |
| 推理引擎 | Core ML（ANE 加速） / ONNX Runtime | macOS 原生加速 / 通用 CPU 推理 |
| 导出格式 | `.mlpackage`（优先） / `.onnx`（兜底） | Core ML 走 ANE，5-15ms；ONNX CPU 20-50ms |
| 分类头 | `BertForSequenceClassification` | 标准序列分类头，输出 intent id + softmax score |

---

## 3. 训练流程

### 3.1 训练数据格式

```yaml
# data/intents.yaml
intents:
  mute:
    - "静音"
    - "别出声"
    - "帮我把电脑静音"
    - "把声音关了"
    - "没声音了"
    - "不想听到声音"
    - "安静"
    - "不要吵"
  volume_up:
    - "音量调大一点"
    - "大声一点"
    - "帮我把那个音量调大一点"
    - "声音太小了"
    - "大点声"
    - "把声音调大"
    - "再大声点"
    - "声音再大一点"
  volume_down:
    - "音量调小一点"
    - "小声一点"
    - "声音太大了"
    - "关小点声"
    - "把声音调小"
    - "小点声"
  open_app:
    - "打开微信"
    - "帮我打开浏览器"
    - "启动 Chrome"
    - "帮我运行计算器"
    - "打开 vs code"
  close_app:
    - "退出微信"
    - "关闭浏览器"
    - "帮我把 Chrome 关了"
    - "退出当前程序"
  ack:
    - "对对对"
    - "没错"
    - "就这个"
    - "可以"
    - "对的"
    - "是的"
  cancel:
    - "算了"
    - "不用了"
    - "不要"
    - "取消"
```

每 intent 至少 8-15 条示例。后续可以随时追加、重训。

### 3.2 训练脚本

```python
# scripts/train_intent_classifier.py
from transformers import (
    BertTokenizer,
    BertForSequenceClassification,
    Trainer,
    TrainingArguments,
)
from datasets import Dataset
import yaml
import torch

# 1. 加载数据
with open("data/intents.yaml") as f:
    data = yaml.safe_load(f)

intent_names = list(data["intents"].keys())
intent2id = {n: i for i, n in enumerate(intent_names)}
texts, labels = [], []
for name, examples in data["intents"].items():
    for ex in examples:
        texts.append(ex)
        labels.append(intent2id[name])

# 2. tokenize
tokenizer = BertTokenizer.from_pretrained("bert-base-chinese")
dataset = Dataset.from_dict({"text": texts, "label": labels})

def tokenize_fn(examples):
    return tokenizer(examples["text"], padding="max_length", truncation=True, max_length=32)

dataset = dataset.map(tokenize_fn, batched=True)

# 3. 训练
model = BertForSequenceClassification.from_pretrained(
    "bert-base-chinese", num_labels=len(intent_names)
)

trainer = Trainer(
    model=model,
    args=TrainingArguments(
        output_dir="./models/action_classifier",
        num_train_epochs=10,
        per_device_train_batch_size=16,
        learning_rate=3e-5,
        save_strategy="epoch",
    ),
    train_dataset=dataset,
)
trainer.train()

# 4. 保存 tokenizer + 模型
model.save_pretrained("./models/action_classifier")
tokenizer.save_pretrained("./models/action_classifier")

# 5. 导出 Core ML（macOS ANE）
import coremltools as ct

dummy_input = torch.randint(0, 30522, (1, 32))  # [CLS] token ids
traced = torch.jit.trace(model.bert, dummy_input)  # 只 trace encoder + 分类头

mlmodel = ct.convert(
    traced,
    inputs=[ct.TensorType(name="input_ids", shape=(1, 32), dtype=np.int32)],
    compute_units=ct.ComputeUnit.ALL,  # 优先 ANE
    minimum_deployment_target=ct.target.macOS  # macOS >= 12
)
mlmodel.save("./models/action_classifier/classifier.mlpackage")
```

### 3.3 训练输出产物

```
models/action_classifier/
├── classifier.mlpackage    # Core ML 模型（优先使用，走 ANE）
├── classifier.onnx         # ONNX 模型（兜底，CPU 推理）
├── config.json             # label <-> id 映射
├── tokenizer.json          # BERT tokenizer
└── vocab.txt               # 词表
```

训练时间（CPU）：~5 分钟（数据量 100-200 条示例时）
推理速度：5-15ms（ANE） / 20-50ms（CPU ONNX）

---

## 4. 推理集成

### 4.1 替换 `local_matcher.py`

```python
# app/core/routing/action_classifier.py
import coremltools as ct
from transformers import BertTokenizer
import numpy as np

# 意图 id ↔ 名称（从训练输出 config.json 加载）
# 意图名称对应数据库中 macro / builtin 的标识符

class IntentClassifier:
    def __init__(self, model_path: str, label_path: str | None = None):
        self.model = ct.models.MLModel(model_path)
        self.tokenizer = BertTokenizer.from_pretrained("bert-base-chinese")

        if label_path:
            import json
            with open(label_path) as f:
                self.id2label = json.load(f)  # {"intent_name": id}
                self.label2id = {v: k for k, v in self.id2label.items()}
        else:
            self.id2label = self.model.get_spec().description.output[0].type.multiArrayType

    def predict(self, text: str) -> tuple[str, float]:
        """返回 (intent_name, confidence)"""
        tokens = self.tokenizer(
            text,
            padding="max_length",
            truncation=True,
            max_length=32,
            return_tensors="np",
        )
        output = self.model.predict({"input_ids": tokens["input_ids"]})
        probs = output["softmax_output"][0]
        idx = int(np.argmax(probs))
        return self.id2label[str(idx)], float(probs[idx])


# intent → handler 映射从 DB 动态加载（不是硬编码）
# macro 表中有 name 字段，与 intent_name 一致
async def load_intent_handlers():
    """从数据库加载 intent → handler 映射"""
    macros = await Macro.find_all().to_list()
    handlers = {}
    for m in macros:
        handlers[m.name] = lambda text, thread_id, m=m: dispatch_macro(m.id, text, thread_id)
    # 内置指令（ack/cancel/end 等）
    handlers.update(BUILTIN_HANDLERS)
    return handlers
```

### 4.2 替换 `LocalMatcher.match()`

```python
# 在 VoiceInputChannel.receive() 中，原来:
#     matcher = await get_local_matcher()
#     l0_match = matcher.match(text)
# 改为:
#     intent_name, confidence = classifier.predict(text)
#     if confidence >= CONFIDENCE_THRESHOLD:  # 0.85
#         # 命中 → 执行对应 handler
#         handler = INTENT_HANDLERS.get(intent_name)
#         if handler:
#             await handler(thread_id, text)
#         return None
#     # 低于阈值 → L0 miss → LLM agent
```

### 4.3 槽位抽取

部分 intent 需要从原始文本中提取参数（如 `open_app("微信")`、`set_volume(delta="+10")`）。分类器只输出 `intent_name`，参数抽取由对应的 handler 负责：

```python
# 每个 handler 自行抽取所需参数
# 方案一：规则抽取（简单场景）
async def handle_open_app(text: str, thread_id: str, app_name: str):
    # "打开微信" → app_name = "微信"
    # "帮我打开Chrome浏览器" → app_name = "chrome"
    ...

# 方案二：BERT TokenClassification（复杂场景，后续迭代）
#   BertForTokenClassification 可学出 "打开[微信](app)" 这样的序列标注
#   适合 slot 模式复杂的场景（多 slot、slot 位置不固定）
```

第一阶段先用规则抽取（prefix/suffix strip），已有现成的 `_verify_app()` / `_verify_delta()` 等函数复用。复杂 slot 场景（如"帮我把微信的窗口调大一点"涉及两个 slot）走第二阶段迭代。

---

## 5. 热更新流程

```
改 data/intents.yaml
  → python scripts/train_intent_classifier.py（2-3 分钟）
  → 覆盖 models/action_classifier/classifier.mlpackage
  → 调用 IntentClassifier.load() 或重启 backend
```

修改意图不需要改任何代码，只改 YAML + 重训。

### 5.1 自动重载

```python
# 监听 model/ 目录变化，自动 reload
from watchdog.observers import Observer

_MODEL_PATH = "models/action_classifier/classifier.mlpackage"
_current_model = None

def get_classifier() -> IntentClassifier:
    global _current_model
    if _current_model is None or model_updated():
        _current_model = IntentClassifier(_MODEL_PATH)
    return _current_model
```

---

## 6. 迁移步骤

| 阶段 | 内容 | 时间估计 |
|------|------|---------|
| 1 | 写 `data/intents.yaml`（从当前 macros 自动导出 + 人工补齐） | 30min |
| 2 | 跑训练脚本 | 5min |
| 3 | 实现 `IntentClassifier` + 替换 `local_matcher.py` | 2h |
| 4 | 接入 slot 抽取 + 老 handler 适配 | 1h |
| 5 | 端到端测试：10 条口语变体测试 | 1h |
| 6 | 回退方案保留：旧 regex L0 作为兜底开关 | 30min |

总计：约 **5 小时** 完成替换。

---

## 7. 回退方案

保留旧 regex L0 作为可切换兜底：

```python
settings = {"l0_mode": "bert"}  # "bert" | "regex"

if settings.l0_mode == "bert":
    intent, conf = classifier.predict(text)
    if conf >= 0.85:
        return handle_intent(intent, text)
elif settings.l0_mode == "regex":
    matcher = await get_local_matcher()
    l0_match = matcher.match(text)
    if l0_match:
        return handle_l0_match(l0_match)
# miss → LLM agent
```

先用 BERT，发现有问题切回 regex 零成本。

---

## 8. 效果对比

| 指令 | 旧 L0（regex 穷举） | 新 L0（BERT 分类器） |
|------|-------------------|--------------------|
| "静音" | ✅ | ✅ |
| "帮我把电脑静音" | 加 trigger 后 ✅ | ✅ 开箱即用 |
| "能把声音关了不" | ❌ | ✅ |
| "帮我把那个音量调大一点" | ❌ | ✅ |
| "声音太大了关小点" | ❌ | ✅ |
| "帮我跑一下 Chrome" | ❌ | ✅ |
| "把微信的窗口调大" | ❌ | ✅（分类 + slot 抽取 fallback LLM）|
| "不想听了先这样吧" | ❌ | 歧义 → fallback LLM ✅ |
| "帮我查一下XXX" | ❌（非 L0 范围） | 歧义 → fallback LLM 正常处理 ✅ |
| 新增一个 macro（无需写代码） | 需写正则/加数据库记录 | 写 5-10 条示例 → 重训 3min ✅ |

---

## 9. 前端导航指令架构

### 9.1 问题

"打开项目管理"、"进入聊天"、"显示设置" 这类指令不是系统命令（不能用 AppleScript），也不是 LLM 问答（不应走 2s 的 Agent）。它们是 **前端页面导航**，需要从 Python → Rust → React 三层桥接。

### 9.2 架构：不走 Macro Engine

调研后端 `app/core/execution/macro/` 后发现：

- `navigate` 虽然是 `MacroActionType` 的枚举值，但只在 **Browser (DOM) source** 下生效（跳转 URL）
- Desktop source 没有 `navigate` 处理分支
- **前端页面导航（React Router 跳转）**和 **浏览器 URL 跳转**是完全不同的概念
- 导航类指令不应走 `run_deterministic`（macro engine 是为浏览器/桌面自动化设计的重型执行器）

**决策：导航指令不经过 `_dispatch_macro()` → `run_deterministic()`，直接在 `_process_single()` 层拦截处理。**

```
voice_input.py _process_single()
  → _resolve_intent() → 返回 ("macro:{id}", args)
  → 加载 macro → 检查 macro_script 的 event_type
  → event_type == "frontend_navigate" ?
      YES → _handle_navigate() ──→ WS voice.navigate
                                      → Rust (通用 fallback 已存在)
                                        → Tauri event "voice:navigate"
                                          → 前端 router.navigate()
      NO  → _dispatch_macro() → run_deterministic() 正常执行
```

### 9.3 全链路

```
用户说"打开项目管理"
  → Tauri ASR → voice.route {text}
  → Python 分类器 → intent: "打开项目管理" (L0 hit, < 10ms)
  → _resolve_intent → DB macro "打开项目管理"
  → 加载 macro → event_type == "frontend_navigate"
  → _handle_navigate(route="/projects")
  → WS voice.navigate {route: "/projects", thread_id: "..."}
  → Rust WS 客户端收到 (voice_session.rs line 249-253 通用 fallback)
  → msg_type "voice.navigate" → 替换 "." 为 ":" → "voice:navigate"
  → event_bus.emit("voice:navigate", body)
  → Tauri event → 前端 useVoiceEvents 监听到
  → router.navigate("/projects")
```

### 9.4 Rust 桥接层：不需要改

`voice_session.rs:249-253` 已有通用 fallback：

```rust
_ => {
    let event_name = msg_type.replace(".", ":");  // voice.navigate → voice:navigate
    event_bus.emit(&event_name, body);              // emit Tauri event
}
```

任何未识别的 `msg_type` 都会自动转为 `:` 格式的 Tauri 事件发射。所以 **Rust 层零改动**。

### 9.5 需要新增/修改的组件

| 层 | 变更 | 文件 | 改动量 |
|----|------|------|--------|
| **Python** | 新增 `_handle_navigate()` 发 `voice.navigate` WS 消息 | `voice_input.py` | ~20 行 |
| **Python** | `_process_single()` 中拦截 `frontend_navigate` 类型 macro | `voice_input.py` | ~10 行 |
| **Python** | 注册器：intent → 路由的映射表 | `voice_input.py` | ~20 行 |
| **Rust** | **不需要改** | — | — |
| **前端** | `useVoiceEvents` 监听 `voice:navigate` → `router.navigate()` | `useVoiceEvents.ts` | ~5 行 |
| **训练数据** | `data/intents.yaml` 加导航意图示例 | `data/intents.yaml` | ~50 行 |
| **DB macro** | 创建 navigate 类型的 macro | `seed_missing_macros.py` | ~30 行 |

### 9.6 消息定义

```json
// Python → Rust → 前端: 导航指令
{
  "type": "voice.navigate",
  "body": {
    "route": "/projects",
    "title": "项目管理",
    "thread_id": "xxx"
  }
}
```

### 9.7 MacroScript 格式

导航类 macro 的 `macro_script` 使用自定义格式：

```yaml
- type: action
  event_type: frontend_navigate
  source: desktop
  payload:
    route: /projects
    title: 项目管理
```

`_process_single` 中检测到 `frontend_navigate` 时，不走 `_dispatch_macro`，直接解析 `payload.route` 并调用 `_handle_navigate()`。

### 9.8 前端路由注册表

```python
# voice_input.py
_FRONTEND_ROUTES: dict[str, str] = {
    "显示主界面":     "/chat",
    "进入聊天":       "/chat",
    "打开项目管理":   "/projects",
    "待办事项":       "/todos",
    "进入学习中心":   "/learning",
    "进入设置":       "/settings",
    "打开设置":       "/settings",
    "管理订阅":       "/subscription",
    "升级":          "/subscription",
    "登录":          "/login",
    "注册":          "/signup",
    "新建对话":      "/chat?new=true",
    # 项目内子页面（需 projectId，暂由 LLM 处理）
    # "打开文件":     "/projects/{id}/files",
    # "查看任务":     "/projects/{id}/tasks",
}
```

### 9.9 实现顺序

| 步骤 | 内容 | 文件 | 依赖 |
|------|------|------|------|
| **1** | Python: 注册表 `_FRONTEND_ROUTES` | `voice_input.py` | 无 |
| **2** | Python: `_handle_navigate()` 方法 | `voice_input.py` | 步骤 1 |
| **3** | Python: `_process_single()` 中拦截导航 macro | `voice_input.py` | 步骤 2 |
| **4** | 前端: 监听 `voice:navigate` → `router.navigate()` | `useVoiceEvents.ts` | 无 |
| **5** | 训练数据: 加导航意图示例 | `data/intents.yaml` | 无 |
| **6** | 训练 + 导出 ONNX | 训练脚本 | 步骤 5 |
| **7** | DB macro: 创建对应 macro 记录 | 种子脚本 | 步骤 1 |
| **8** | 端到端测试 | 手动测试 | 全部完成 |

---

## 10. 宏自动化系统排障记录

### 10.1 修复的问题

| # | 问题 | 文件 | 根因 | 修复 |
|---|------|------|------|------|
| 1 | **CGEvent 点击无效** | `_actions.py` | `kCGEventLeftMouseDown = 5`（实际是 `kCGEventMouseMoved`），全局所有鼠标点发送的是移动事件 | 改为 `Quartz.kCGEventLeftMouseDown`（值为 1） |
| 2 | **OCR 坐标偏移（缩放模式）** | `_info.py` | `get_ui_scale_factor()` 用 `pixel_w / log_w` 计算，缩放模式下返回 0.6，坐标被放大 1.67x | 改用 `CGDisplayBackingScaleFactor()` |
| 3 | **OCR 模糊匹配阈值失效** | `_element_mixin.py` | 精确匹配命中时 `best_r` 未更新（仍为 0.0），`best_r >= 0.5` 判断失败 | 精确匹配后设置 `best_r = 1.0` |
| 4 | **Vision Router 冷启动** | `router.py` | 首次 `vision_engine.process()` 调用时 OCR provider 延迟加载，返回 None | 直调 `ocr_provider.process()` 可绕过 |

### 10.2 宏 381 流程（创建腾讯会议 → 复制邀请信息）

```
1. applescript: 清剪贴板 → activate TencentMeeting → delay 8s
2. click "快速会议": OCR 裁剪窗口 → 找到文字 → CGEvent 点击
3. wait 10s
4. click "邀请": OCR 全屏（会议窗口不在主窗口内）→ 找到文字 → CGEvent 点击
5. wait 5s
6. click "复制全部信息": OCR 全屏（邀请面板为浮层）→ 找到文字 → CGEvent 点击
7. wait 2s
8. applescript: Cmd+W 关闭邀请面板
9. applescript: 验证剪贴板非空
```

### 10.3 宏 382 流程（发送会议信息到微信）

```
1. applescript: activate WeChat + reopen → delay 2s → Cmd+F 搜索
2. wait 2s
3. applescript:
   savedClip = clipboard          ← 保存会议信息
   clipboard = "{{ contact }}"    ← 写入联系人名
   Cmd+V 粘贴 → Enter             ← 搜索联系人
   clipboard = savedClip          ← 恢复会议信息
   Cmd+V 粘贴 → Enter             ← 发送
```

### 10.4 经验总结

1. **`_actions.py` 是系统核心**——`click()`、`double_click()` 被 DesktopController、MacroEngine、find_element 等多个模块调用，一个常量错误导致全局点击失效。
2. **Electron 应用需要鼠标光标物理移动**——CGEvent 只发事件不移光标，部分 Electron/Chromium 不响应。修复：先发 `kCGEventMouseMoved` 再发 `kCGEventLeftMouseDown/Up`。
3. **OCR 裁剪策略**——主窗口用裁剪窗口 OCR（精度高），子窗口/浮层面板用全屏 OCR（避免 `get_current_app()` 返回错误边界）。
4. **宏链剪贴板管理**——前一个宏的输出（会议信息）存在剪贴板，后一个宏不能直接覆盖。用 `savedClip` 暂存恢复。

### 10.5 宏 383 流程（预定会议 → 设置日期时间 → 复制邀请信息）

```yaml
- type: action
  event_type: applescript
  source: desktop
  payload:
    script: |
      set the clipboard to ""
      tell application "TencentMeeting" to activate
      delay 8
- type: action
  event_type: click
  source: desktop
  payload:
    element_name: "预定会议"
- type: action
  event_type: wait
  source: desktop
  payload:
    duration: 3000
- type: action
  event_type: applescript
  source: desktop
  payload:
    script: |
      tell application "System Events" to keystroke tab
      delay 0.5
      set the clipboard to "{{ date }}"
      tell application "System Events"
        keystroke "a" using command down
        delay 0.3
        keystroke "v" using command down
      end tell
      delay 0.5
      tell application "System Events" to keystroke tab
      delay 0.5
      set the clipboard to "{{ time }}"
      tell application "System Events"
        keystroke "a" using command down
        delay 0.3
        keystroke "v" using command down
      end tell
- type: action
  event_type: wait
  source: desktop
  payload:
    duration: 2000
- type: action
  event_type: ax_press
  source: desktop
  payload:
    bundle_id: "com.tencent.meeting"
    role: "AXButton"
    label: "预定"
    ax_action: "AXPress"
- type: action
  event_type: wait
  source: desktop
  payload:
    duration: 5000
- type: action
  event_type: click
  source: desktop
  payload:
    element_name: "仍然预定"
    optional: true
- type: action
  event_type: wait
  source: desktop
  payload:
    duration: 3000
- type: action
  event_type: click
  source: desktop
  payload:
    element_name: "复制全部信息"
- type: action
  event_type: wait
  source: desktop
  payload:
    duration: 2000
- type: action
  event_type: applescript
  source: desktop
  payload:
    script: |
      tell application "System Events"
        tell process "TencentMeeting"
          keystroke "w" using command down
        end tell
      end tell
- type: action
  event_type: applescript
  source: desktop
  payload:
    script: |
      set clip to (the clipboard as text)
      if clip is "" then
        error "Clipboard empty after meeting"
      end if
```

#### 宏 383 关键设计点

| # | 设计 | 说明 |
|---|------|------|
| 1 | **AppleScript 激活 vs `open -a`** | `tell app "TencentMeeting" to activate` + `delay 8` 是因为 `open -a` 无法可靠等待 App 窗口完全就绪；已有会议重启后 `get_current_app()` 可能返回 `0,0,0,0` 边界 |
| 2 | **日期/时间通过 Cmd+V 粘贴** | Electron `<input>` 字段不支持 AppleScript `keystroke` 输入字符，但 `Cmd+A` 全选 + `Cmd+V` 粘贴有效。先 `keystroke tab` 聚焦字段再粘贴 |
| 3 | **`optional: true` 冲突处理** | 新建会议若与现有会议时间冲突，TencentMeeting 弹出"仍然预定"确认按钮。用 `optional: true` 标记 —— OCR 找不到时跳过不报错，找到时点击 |
| 4 | **AXPress 选择 Electron 按钮** | Electron 对话框按钮没有 CGEvent 响应（不处理鼠标事件），必须用 `ax_press` 通过 Accessibility API 触发 `AXPress` action |
| 5 | **OCR 精确匹配防干扰** | OCR 有时返回 `"预定会议～"`（末尾带符号），精确匹配 `el.text.strip() == "预定会议"` 会失败。解决方案：`rstrip('～~!@#$%')` 清洗 OCR 文本后再比较 |
| 6 | **窗口 `bounds=0,0,0,0` 重试** | App 冷启动时 `get_current_app()` 可能返回零边界，`_try_ocr` 循环 8 次 × 1s 等待窗口就绪 |
| 7 | **Cmd+W 关闭面板** | 邀请面板只能通过 `Cmd+W` 关闭（Escape 和鼠标点击无效）|
| 8 | **剪贴板验证** | 最后一步检查剪贴板非空，防止"复制全部信息"因 OCR 误点空面板而粘贴空白 |

#### 冲突处理验证结果

| 场景 | 条件 | "仍然预定"行为 | 结果 |
|------|------|--------------|------|
| 无冲突 | 时间段无已有会议 | OCR 找不到 → `optional` 跳过 → `WARNING` 日志 | ✅ 继续执行 |
| 有冲突 | 同一时间段已有会议 | OCR 精确匹配 → 点击确认 | ✅ 继续执行 |

---
