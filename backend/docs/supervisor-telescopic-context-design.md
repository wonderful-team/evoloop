# Supervisor 上下文伸缩化与 L0 意图驱动上下文设计方案

## 1. 背景与问题

在近几轮对 Supervisor 节点的评估与改造中，我们逐步验证了一个核心矛盾：

> **Supervisor 既需要足够的信息做正确决策，又不能把全量上下文都塞进 Prompt。**

最初的问题非常明显：Supervisor 被配置了 `search_web`、`list_dir`、`read_file` 等执行类工具，导致它越过 triage 边界直接执行。经过改造后，工具边界被收紧，但随之暴露出新问题：

- 环境、设备等“简单事实”问题因为没有上下文，被迫派给 Worker；
- 为了回答这些问题，我们又往环境摘要里加了越来越多字段；
- 如果不改变结构，未来每新增一类场景，都会让 Supervisor 的上下文继续膨胀，重新走回老版“Prompt 越来越大”的老路。

因此，本轮讨论的核心目标是：

> **把 Supervisor 的上下文从“全量堆叠”改为“按意图按需加载”，在保持决策正确率的前提下，让上下文长度可控、可扩展、可预测。**

---

## 2. 测试结论与现状数据

### 2.1 评估方法

- **题目**：175 道，覆盖 17 大类（chitchat、simple_task、complex_task、query、memory、medical、finance、research、coding、ops、education、news、weather、environment、ambiguous、multi_intent、edge）
- **模型**：`deepseek-v4-flash`
- **观测指标**：只记录 Supervisor 的**第一次动作**，随后立即 stop，避免 Worker 实际执行
- **动作分类**：`direct_answer` / `route_to_worker` / `list_macros` / `run_macro` / `memory_tool` / `ask_human` / `direct_tool:*` / `no_action_timeout`

### 2.2 三轮改造结果对比

| 第一动作 | 初始基线 | 移除执行工具 + 收紧 Prompt | 补充环境实时信息（最新） |
|---|---|---|---|
| `direct_answer` | 87 (49.7%) | 99 (56.6%) | **111 (63.4%)** |
| `route_to_worker` | 0 (0%) | 48 (27.4%) | 44 (25.1%) |
| `list_macros` | 48 (27.4%) | 8 (4.6%) | 7 (4.0%) |
| `memory_tool` | 6 (3.4%) | 14 (8.0%) | 9 (5.1%) |
| `direct_tool`（search_web/list_dir/list_agents） | 33 (18.9%) | 1 (0.6%) | 1 (0.6%) |
| `ask_human` | 0 | 3 (1.7%) | 3 (1.7%) |
| `no_action_timeout` | 1 (0.6%) | 2 (1.1%) | 0 |
| **合计** | **175** | **175** | **175** |

关键结论：

1. **直接回答率从 49.7% 提升到 63.4%**，说明更多简单问题被留在 Supervisor 层解决。
2. **越权执行工具从 18.9% 降到 0.6%**，只剩一次 `list_agents` 误触发。
3. **宏调用从 27.4% 降到 4%**，基本收敛到真正明确的单步自动化（打开计算器、设置提醒等）。
4. **约 25% 的问题正确路由到 Worker**，集中在复杂任务、实时信息、代码/文件操作等。

### 2.3 当前仍存在的典型问题

| 问题 | 案例 | 根因 |
|---|---|---|
| 设备类问题误触发 `list_agents` | “有哪些设备连接了” | Supervisor 还持有 `list_agents`，但用户要的是完整设备发现，不是 Agent 列表 |
| 部分环境信息仍需派 Worker | “我的电脑型号是什么”“浏览器打开了哪些标签” | 环境摘要里没有这些字段 |
| 上下文会持续膨胀 | 每加一类新场景就要往环境摘要/静态 Prompt 里塞内容 | 缺少按意图动态加载的机制 |
| L0 只服务语音 | chat 入口没有 L0 预分类 | 所有意图判断全靠 LLM 从零推理 |
| 多轮场景未处理 | 指代消解、上下文继承 | 不在本次范围，但需提前预留架构 |

### 2.4 回归测试结论

每次改造后运行核心测试：

```bash
uv run pytest tests/unit/end_to_end \
  tests/unit/core/engine/test_agent_macro_conversation.py \
  tests/unit/core/engine/test_route_to_tool_allowlist.py -v
```

结果曾为：**41 通过，1 失败**。失败用例 `test_route_by_next_node_follows_state` 是因为
`app/core/engine/routers.py` 确实缺少 `route_by_next_node` 函数（被
`agent_main.yaml` 引用）。**本轮已修复该函数**，该失败不再属于预存在噪音。

---

## 3. 设计目标

| 目标 | 说明 | 衡量方式 |
|---|---|---|
| **G1: 上下文长度可控** | 新增场景不应让每次请求的上下文都变大 | 按意图统计平均 context ticket 长度 |
| **G2: 决策准确率不下降** | 直接回答、正确路由、合理 ask_human 的比例保持稳定或提升 | 175 题评估中 `direct_answer` + `route_to_worker` + `ask_human` 占比 |
| **G3: Supervisor 不越权执行** | 搜索、文件、代码、系统操作等应路由到 Worker 或由宏代理 | `direct_tool:*` 趋近于 0 |
| **G4: 简单环境任务不出 Supervisor** | 运行中的应用、网络状态、磁盘等应通过上下文直接回答 | environment 类直接回答率 |
| **G5: 可扩展性** | 新增场景只需要新增一个 ContextProvider，不污染所有请求 | 新增 provider 时，无关意图的平均 context 长度不变 |
| **G6: 为多轮/指代消解预留接口** | L0 和 Provider 都支持会话状态输入 | 后续可接入 `session_history` / `coreference_resolution` |

---

## 4. 整体架构（已复用现有基础设施）

> 评审后确认：系统**已经**具备大部分所需基础设施，不需要再新建一套 `ContextProvider` 抽象。
> 本轮改造的核心是“把现有零件正确连起来”而不是“重新造轮子”。

```text
User Message
    │
    ▼
┌─────────────────────────────────────────┐
│  USER_PROMPT_SUBMIT hook                │
│  · 入口统一触发（chat / resume / voice）   │
│  · 由 L0 CommandRouter 产出 IntentHint    │
│  · 结果写入 EvoContext.metadata           │
└─────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────┐
│  已有 ContextPlugin registry            │
│  · 通过 is_needed(intent) 按需执行        │
│  · EnvironmentContextPlugin（重）         │
│  · ProjectStateContextPlugin / ProjectContextPlugin
│  · 未来新增 plugin 只需实现 is_needed      │
└─────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────┐
│  LayeredContextCache + 静态索引           │
│  · active_skills / active_macros / operation_map
│  · environment_telemetry 由 plugin 按需生成  │
└─────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────┐
│  Dynamic Context Ticket                   │
│  · Base Context（始终加载）               │
│  · Module A（按需）                       │
│  · Module B（按需）                       │
└─────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────┐
│  Supervisor LLM                           │
│  · 基于精简上下文决策                      │
│  · 可覆盖 L0 建议，可 ask_human / route_to  │
└─────────────────────────────────────────┘
```

已存在并被复用的关键组件：

| 已有组件 | 位置 | 本轮用途 |
|---|---|---|
| `ContextPlugin` 协议 + `plugin_registry` | `app/core/context/plugins.py` | 作为按 intent  gated 的 Provider 入口 |
| `LayeredContextCache` / `StaticContextLayer` | `app/core/context/cache.py` | 静态索引缓存，动态层保持新鲜 |
| `SkillHydrator` | `app/core/engine/skill_hydrator.py` | 作为 SkillProvider，支持 eager/lazy |
| `USER_PROMPT_SUBMIT` hook | `app/core/engine/hooks/core.py` | 统一接入 L0 分类 |
| `_filter_messages_for_supervisor` / `ContextTrimmer` | 已有 | 控制 Supervisor 上下文长度 |

核心变化：

- **以前是“先加载全部，再让 LLM 自己挑”**；
- **以后是“L0 先判断需要什么，再只加载相关的”**；
- **实现上不是新建 `ContextProvider`，而是给现有 `ContextPlugin` 加 `is_needed(intent)` 门控**。

---

## 5. 详细设计

### 5.1 L0 意图分类器（chat 扩展）

现状：

- `app/core/routing/action_classifier.py` 是 BERT ONNX 分类器，目前**只服务于语音 L0 路由**。
- `app/core/routing/local_matcher.py` 和 `RouteCatalog` 是语音客户端本地匹配用的。
- chat 入口完全没有 L0 分类。

设计：

新增/扩展一个面向 chat 的 L0 分类器，可以命名为 `chat_intent_classifier`（位置待定，建议 `app/core/routing/chat_intent_classifier.py` 或复用 `app/core/engine/intent.py`）。

**意图标签**：

| 标签 | 说明 | 示例 |
|---|---|---|
| `direct_answer` | 问候、能力说明、百科知识等 | “你好”“光速是多少” |
| `environment_query` | 询问本机环境/系统/运行状态 | “现在有哪些程序在运行” |
| `memory_query` | 询问历史对话或项目记忆 | “我之前问过你什么” |
| `macro_task` | 明确的单步/短自动化任务 | “打开计算器”“5 分钟后提醒我” |
| `worker_task` | 复杂执行、代码、实时信息、多步任务 | “写一个知乎爬虫”“今天有什么新闻” |
| `multi_intent` | 一句话包含多个独立目标 | “打开 Chrome 然后搜索新闻” |
| `ask_human` | 参数缺失或任务不明确 | “帮我” |
| `ambiguous` | 置信度低，需要更多上下文 | “ ??? ” |

**实现策略（MVP → 长期）**：

1. **MVP**：基于规则 + 关键词 + 我们已有 175 道题的 category 映射，快速验证架构。
2. **中期**：扩展 `action_classifier.py` 的 ONNX 模型，增加 chat 标签，重新训练。
3. **长期**：结合会话历史、运行中 Worker、项目状态做上下文感知分类。

**输出结构**：

```python
class IntentHint(BaseModel):
    intent: str                      # 上述标签之一
    confidence: float                # 0.0 ~ 1.0
    suggested_modules: list[str]     # 建议加载的 ContextProvider 名称
    reason: str                    # 简要说明
    sub_intents: list[IntentHint] | None  # multi_intent 时使用
```

### 5.2 L0 与 chat 入口的集成（改为 Hook 驱动）

L0 分类不应该放在 HTTP 路由层重复实现。统一接入点：

```python
# app/core/engine/dispatch.py
hook_ctx = HookContext(
    thread_id=thread_id,
    project_id=project_id,
    metadata=HookMetadata(
        prompt=message_content,
        source=source or "chat",
        intent_hint=metadata.get("intent_hint"),
    ),
)
hook_result = await hook_system.trigger(HookEvent.USER_PROMPT_SUBMIT, hook_ctx)
```

`app/core/engine/hooks/handlers/user.py` 中的默认 `user_prompt_submit_handler` 负责：

1. 如果入口（如 `_chat.py` 为 fast-path 本地动作已跑过 L0）已经传入 `intent_hint`，则直接复用；
2. 否则调用 `CommandRouter.resolve(...)` 做轻量分类；
3. 将结果写入 `context.metadata.intent_hint`，并回写到 graph inputs 的 `metadata` 中。

`chat` 入口仍然可以先跑 L0 处理本地 macro / builtin / navigation 命中，但只需把 `intent_hint` 交给 dispatch；agent 路径不再需要重复分类。

### 5.3 从 ContextProvider 到已有 ContextPlugin 的门控扩展

评审结论：不需要新建 `ContextProvider` 抽象，系统已经有 `ContextPlugin` 协议和 `plugin_registry`。

扩展方式：

```python
class ContextPlugin(Protocol):
    def hydrate(self, ctx: EvoContext) -> None: ...
    # 可选扩展
    def is_needed(self, intent: str | None) -> bool: ...
```

`plugin_registry.hydrate_context(ctx, intent=intent)` 会：

- 若插件实现了 `is_needed` 且返回 `False`，则跳过该插件；
- 未实现 `is_needed` 的插件保持“始终加载”，兼容所有已有插件。

已落地的门控示例：

| 插件 | 负责内容 | 默认加载 |
|---|---|---|
| `EnvironmentContextPlugin` | CPU、内存、磁盘、网络、运行应用、Docker、服务、active_window | 仅当 `intent` 可能涉及环境/系统/宏/Worker |
| `ProjectStateContextPlugin` | active plan、todo | 跳过 `direct_answer` / `environment_query` |
| `ProjectContextPlugin` | project_id / working_directory 同步 | 始终加载（基础设施） |

未来新增插件只需要：

1. 实现 `ContextPlugin`；
2. 若数据较贵，再实现 `is_needed(intent)`。

### 5.4 意图 → 模块映射

| 意图 | 加载 Provider | 不加载 |
|---|---|---|
| `direct_answer` | Base | 全部 |
| `environment_query` | Base + Environment | Memory, Macro, Skill, Project |
| `memory_query` | Base + Memory | Environment, Skill, Project |
| `macro_task` | Base + Macro + Environment（若时间相关） | Skill, Project |
| `worker_task` | Base + Skill + Project +（可选 Environment） | Memory, Macro |
| `multi_intent` | Base + Union（按子意图） | 无关模块 |
| `ask_human` | Base + 相关模块 | 无强制 |
| `ambiguous` | Base + Memory + Environment（保守兜底） | Skill 全量、Macro 全量 |

说明：

- `multi_intent` 拆解为子意图后，取各子意图所需模块的并集。
- `worker_task` 如果涉及系统操作（如“重启 Nginx”），可额外加载 Environment 摘要。

### 5.5 Fallback 策略

L0 置信度低时，不能盲目少加载上下文，否则 Supervisor 会缺信息乱猜。

| 置信度 | 策略 |
|---|---|
| `>= 0.8` | 严格按 `suggested_modules` 加载 |
| `0.5 ~ 0.8` | 加载 `suggested_modules` + Memory（辅助理解） |
| `< 0.5` | 加载 Base + Memory + Environment（最小安全集），让 Supervisor 自己决定 ask_human / route_to |

Prompt 中需要明确：

> “The context sections below were selected based on a preliminary intent hint. If the provided context is insufficient for the user's request, do not hallucinate — ask the user for clarification or route to Worker.”

### 5.6 Supervisor Prompt 调整

在 `supervisor.prompt.j2` 中增加/调整以下章节：

1. **Environment-Aware Direct Answers**：如果环境摘要中有答案，直接回答。
2. **Macro-First Protocol（仅限明确短自动化）**：只有单步、无副作用、匹配宏时才用宏。
3. **Multi-Intent Handling**：多意图不要走单个宏，路由到 Worker。
4. **L0 Hint Awareness**：L0 建议仅供参考，最终判断以用户原文为准。
5. **Ask Human 鼓励**：参数不明时优先 ask_human，而不是猜测或乱派 Worker。

### 5.7 宏与设备发现

针对“有哪些设备连接了”这类问题，设计一个全局系统宏：

- **宏名**：`discover_connected_devices`
- **触发词**：「有哪些设备连接了」「连了哪些设备」「网络里有哪些设备」「有哪些设备」等
- **作用域**：全局（`project_id = NULL`），`is_active = true`，`status = verified`
- **实现方式**：新增 `bash` 宏引擎 step，让宏脚本可以执行只读 shell 命令；A2A 节点查询复用内部工具逻辑，封装为独立的辅助脚本 `scripts/discover_a2a_agents.py` 由宏调用。
- **脚本内容**：多步执行
  1. `python3 scripts/discover_a2a_agents.py` — 获取当前 Agent 网络中的在线节点（输出到 `online_agents`）
  2. `adb devices -l` — 获取已连接的 Android 设备（输出到 `mobile_devices`）
  3. `arp -a` — 获取局域网 ARP 表（输出到 `local_network`）
  4. 三份输出通过 `extracted_data` 汇总返回给 Supervisor

这样 Supervisor 只需要调用 `list_macros` + `run_macro(macro_name="discover_connected_devices")`，无需直接持有 `list_agents` 或 `execute_command`。

**注意**：`list_agents` 本身仍作为 A2A Worker 工具保留；只是不再暴露给 Supervisor，避免设备类问题误触发。

### 5.8 环境摘要补充（修复数据链）

在 `EnvironmentContextPlugin`（即 `app/core/environment/context_plugin.py` + `prompt.py`）中补充并修正：

- `running_apps`：从 `[:5]` 扩展到 `[:20]`，并在模板层取消二次截断；
- `active_window`：通过 `macos_driver.get_current_app()` 在 `build_environment_summaries` 中生成，模板已引用该字段；
- `current_time`：保留；
- 保留 `cpu_percent`、`memory_percent`、`disk_space`、`network`、`docker_containers`、`running_services`。

**不再提供的字段**：

- `top_processes`：原模板引用但数据从未生成，属于死分支，已移除；
- 完整 `installed_apps` 列表：这是“查询”行为，不应塞进每次 Supervisor Prompt。

`AgentContextHydrator` 中原先重复采集环境 telemetry 的代码已被移除：环境数据统一由 `EnvironmentContextPlugin` 提供，避免 `get_awakened_state` 与 `macos_driver` 在静态层重复调用。

### 5.9 多轮 / 指代消解（预留接口，下一步讨论）

本次设计不实现多轮语义理解，但为后续预留：

- `IntentHint` 可扩展 `session_history` 输入；
- `ContextProvider` 可接收 `previous_intent` 和 `coreference_resolved_message`；
- 新增 `CoreferenceProvider` 专门处理指代消解，按需加载历史上下文。

典型场景：

- 用户说“打开计算器”，下一轮说“然后截个图” → 需要理解“然后”承接上一目标。
- 用户说“把这个文件删掉”，需要消解“这个文件”指代的是哪个。

这类问题将在 L0 框架稳定后，作为 `multi_intent` / `coreference` 子模块单独处理。

---

## 5.10 路由层统一评估：chat/voice 是否共用 L0

> 结论：**可以统一 L0 的“决策/匹配”层，但不能统一“输出/呈现”层；需要先做一次“决策与通道副作用分离”的重构。**

### 5.10.1 当前代码路径

| 通道 | 入口 | 路径 |
|---|---|---|
| chat | `POST /chat` (`app/api/routes/agent/_chat.py`) | `web_input.receive` → `web_input.dispatch` → `dispatch_agent_run`，**没有 L0 预分类** |
| voice | `WS /voice` (`app/api/routes/voice_ws.py`) | `voice_input.receive` → `process_single` (L0) → 本地命中由 `voice_executor` 推 TTS/Navigate，未命中才走 Agent |

### 5.10.2 哪些层是通道无关的，哪些是通道绑定的

**通道无关（可共用）**

- `app/core/routing/init_spec.py`：从后端源（apps、macros、atlas）构建的**动作目录**，只是命名上叫 `RouteCatalog`。
- `app/core/routing/local_matcher.py`：基于模板、槽位、别名、拼音的确定性匹配器，无语音专属逻辑。
- `app/core/routing/action_classifier.py`：BERT ONNX 分类器，当前标签是语音 L0 动作，但模型本身可扩展为通用 L0 标签。
- `app/core/routing/channels/voice.py` 中的**匹配逻辑**（direct routes、aliases、BERT、local matcher）。

**通道绑定（不可直接共用）**

- `app/core/routing/executor.py`：直接依赖 `manager`（WebSocket）、`voice_state_machine`、Volcengine TTS、`voice.navigate` 信封、TTS 推送。
- `channels/voice.py` 中的 `resolve_intent`：匹配成功后直接调用 `handle_navigate` / `dispatch_macro` / `handle_builtin`，属于“执行”而不是“返回决策”。
- `voice_input.py` 的 `post_dispatch`：注册 Worker 后还要在 WebSocket 上异步推送结果和状态。

### 5.10.3 直接合用的阻塞点

| 阻塞点 | 说明 | 改造量 |
|---|---|---|
| `executor.py` 输出绑定语音 | `push_voice_result`、`push_tts_text`、`voice_state_machine` 都假设最终输出是语音流 | 中 |
| `channels/voice.py` 执行即返回 | `resolve_intent` 直接触发副作用，不返回通道无关的决策对象 | 中 |
| `RouteCatalog` 命名/语义 | 语义是语音客户端契约，实际是通用路由目录 | 小 |
| chat 缺少本地执行策略 | 例如“打开计算器”在 chat 里是否应执行本地应用，需要产品/UX 决策 | 决策成本 |
| 执行模式差异 | voice 是 WebSocket 长连接异步 push；chat 是 HTTP 请求-响应或后台任务 | 中 |

### 5.10.4 推荐统一路径

把现有路由层拆成三层：

```text
User Message (chat / voice / mobile)
        │
        ▼
┌────────────────────────────────────┐
│ Layer0 Router（通道无关）            │
│ · RouteCatalog（原 RouteCatalog）  │
│ · 匹配器：LocalMatcher + BERT       │
│ · 输出：RouteDecision               │
│   target_type ∈ {local, macro, builtin, agent}
│   target, params, confidence, intent_hint
└────────────────────────────────────┘
        │
        ▼
┌────────────────────────────────────┐
│ Channel Adapter（通道相关）          │
│ voice → TTS / navigate / WS push   │
│ chat  → HTTP/SSE / 后台任务         │
│ mobile → push / native bridge       │
└────────────────────────────────────┘
        │
        ▼
┌────────────────────────────────────┐
│ Agent Engine（L0 未命中时）          │
│ Supervisor / Worker                 │
└────────────────────────────────────┘
```

### 5.10.5 与 L0 + ContextProvider 架构的关系

- `RouteDecision` 中同时携带 `intent_hint`（用于选择 ContextProvider），这样**一次 L0 调用同时服务“路由决策”和“上下文选择”**。
- chat 入口先接入 `intent_hint`（即第 5.2 节设计），不强制接入本地 macro 执行；等通道无关重构完成后，再按需打开 chat 的 local/macro 执行能力。
- 统一的价值不是让 chat 走语音 TTS，而是**让 voice 和 chat 共用同一套动作目录和匹配逻辑**，避免 Supervisor 在两端重复判断宏、设备、内置命令。

### 5.10.6 建议的实施顺序

1. **Phase 1 完成后**：把 Supervisor 的 `list_agents` 和设备发现宏收尾，确保 L0 目录稳定。
2. **Phase 2 期间**：定义 `RouteDecision` 和 `CommandRouter` 接口，但保持 `channels/voice.py` 现有行为不变（内部做 adapter）。
3. **Phase 3**：chat 接入 `IntentHint` 用于 ContextProvider 选择；此时已有统一的 L0 入口。
4. **Phase 4 或后续**：若产品决定 chat 可执行本地 macro，则复用 `RouteDecision` + `channel policy` 实现，而不需要为 chat 再写一套匹配逻辑。

### 5.10.7 已落地实现（本次改造）

- 新增 `app/core/routing/command_router.py`：
  - 通道无关的 `CommandRouter.resolve()`。
  - 输出 `RouteDecision`（含 `target_type`/`target`/`params`/`confidence`/`intent_hint`）。
  - 整合 direct routes、route aliases、BERT 意图、LocalMatcher 兜底。
- 新增 `app/core/routing/actions.py`：
  - 通道无关的宏/内置命令执行：`run_macro` / `run_builtin`。
  - 返回 `ActionOutcome`，不再关心 TTS/WS/HTTP 输出。
- 新增 `app/core/routing/channels/web.py`：
  - chat 通道的 L0 执行适配器：macro、builtin、navigation 直接返回，非导航 local 动作委托给 Agent。
- 改造 `app/core/routing/channels/voice.py`：
  - 仅保留 voice 的 thin adapter：调用 `CommandRouter` + `actions` + voice executor。
- 改造 `app/core/routing/executor.py`：
  - `dispatch_macro` / `handle_builtin` 改为对 `actions.py` 的封装，保持原有 voice 输出签名。
- 改造 `app/core/routing/schemas.py`：
  - 增加 `IntentHint` / `RouteDecision` 字段 / `RouteCatalog = RouteCatalog` 别名。
- 改造 `app/api/routes/agent/_chat.py`：
  - 每个 chat 请求先过 `CommandRouter`。
  - 把 `intent_hint` 写入 `msg.metadata`，供后续 `ContextHydrator` 动态选择 Provider。
  - 对 macro/builtin/navigation 走 web adapter 立即返回；其余走 Agent。
- 改造 `app/core/routing/init_spec.py`：
  - 返回 `RouteCatalog`（`RouteCatalog` 别名），语义上不再仅属于语音。

---

## 6. 实施阶段

### Phase 1：修复真实坏味道与坏边（立即收益）

1. 修复 `app/core/engine/routers.py` 中缺失的 `route_by_next_node`（`agent_main.yaml` 已引用）。
2. 修复环境数据链：
   - `app/core/environment/prompt.py` 生成 `active_window`；
   - `running_apps` 上限从 5 调整到 20；
   - 移除 `supervisor_environment_summary.j2` 中 `top_processes` 死分支；
   - `AgentContextHydrator` 不再重复采集环境 telemetry，统一交给 `EnvironmentContextPlugin`。
3. 清理本次改动中触及的 6 元组伪捕获（`except (ValueError, OSError, RuntimeError, TypeError, KeyError, AttributeError)`），改为具体异常或带 `exc_info` 的日志。

### Phase 2：复用 ContextPlugin + Hook 接入 L0（架构收敛，无行为变化）

1. 扩展 `ContextPlugin` 协议：允许可选实现 `is_needed(intent) -> bool`；
2. `plugin_registry.hydrate_context(ctx, intent=intent)` 按门控跳过不需要的插件；
3. 给 `EnvironmentContextPlugin` 和 `ProjectStateContextPlugin` 添加 `is_needed` 实现；
4. 在 `app/core/engine/dispatch.py` 中统一触发 `USER_PROMPT_SUBMIT` hook；
5. `app/core/engine/hooks/handlers/user.py` 在 hook 中调用 `CommandRouter` 产出 `intent_hint`（若入口已提供则复用）；
6. `AgentContextHydrator` 从 `config.metadata.intent_hint` / `ctx.metadata.intent_hint` 读取意图，并传给 `plugin_registry`；
7. 默认保持“未提供 intent 时全量加载”，确保现有测试不失败；
8. 跑测试和评估，确认无回归。

### Phase 3：L0 阈值评估与模型优化

1. 根据 175 题评估调优意图映射表和 fallback 阈值；
2. 将规则分类器迁移到扩展后的 ONNX 模型（`action_classifier.py` 增加 chat 标签）；
3. 观察并优化：
   - 每类意图下的平均 context 长度；
   - 直接回答率、路由准确率、ask_human 率；
   - 环境/设备类问题是否仍误路由到 `list_agents`。

### Phase 4：多轮 / 指代消解（预留接口）

1. 在 `IntentHint` 中启用 `previous_intent` / `session_history` 字段；
2. 扩展 `is_needed` 接口以支持多轮 context（如 `multi_intent` 子意图拆解）；
3. 新增 `CoreferencePlugin` 专门处理指代消解，按需加载。

3. 处理多轮场景中的 `multi_intent` 边界情况。
4. 建立长期指标看板：context 长度、latency、正确率。

---

## 7. 风险与影响

| 风险 | 影响 | 缓解措施 |
|---|---|---|
| L0 分类错误 | 加载了错误的上下文，Supervisor 可能误判 | fallback 兜底 + Prompt 允许 Supervisor 覆盖 L0 建议 |
| 环境 Provider 变慢 | 每次调用 AppleScript / 进程遍历，按需后峰值延迟增加 | 对 Environment 输出做 TTL 缓存（如 5 秒）；去掉 `top_processes` |
| 多意图模块爆炸 | `multi_intent` 加载多个模块，context 反而更大 | 子意图拆解 + 只加载必要并集；避免无限扩展 |
| 测试回归 | 现有测试可能依赖全量上下文 | Phase 2 默认全量加载；逐步切换 |
| 维护成本增加 | 新增 Provider 和意图标签需要管理 | 意图标签从 175 题 category 自然映射，Provider 按功能拆分 |

---

## 8. 相关文件与评估产物

### 已改动的文件

- `backend/app/core/engine/config/agent_main.yaml` — Supervisor 工具边界
- `backend/app/config/templates/core/engine/supervisor.prompt.j2` — Supervisor 决策规则（设备发现走宏）
- `backend/app/core/execution/macro/schemas.py` — 新增 `BASH` step / action 类型及风险分级
- `backend/app/core/execution/macro/engine/_bash.py` — bash step 执行器
- `backend/app/core/execution/macro/engine/__init__.py` — 引擎接入 `BASH` 分支
- `backend/scripts/seed_global_macros.py` — 新增 `discover_connected_devices` 全局宏
- `backend/scripts/discover_a2a_agents.py` — 宏使用的 A2A 节点发现辅助脚本
- `backend/app/core/engine/context_hydrator.py` — 按 `intent` 门控静态层加载
- `backend/app/core/context/cache.py` — 静态缓存 key 加入 `intent`
- `backend/app/core/environment/context_plugin.py` — 实现 `is_needed` 并清理异常捕获
- `backend/app/core/environment/prompt.py` — 生成 `active_window`、扩展 `running_apps` 上限、清理异常捕获
- `backend/app/core/project/context_plugins.py` — 实现 `is_needed` 并清理异常捕获
- `backend/app/config/templates/core/engine/fragments/supervisor_environment_summary.j2` — 移除 `top_processes` 死分支，取消 `running_apps` 二次截断
- `backend/app/core/routing/command_router.py` — 通道无关 L0 路由决策
- `backend/app/core/engine/routers.py` — 补回 `route_by_next_node`
- `backend/app/core/engine/dispatch.py` — 统一触发 `USER_PROMPT_SUBMIT` hook，传递并回写 `intent_hint`
- `backend/app/core/engine/hooks/handlers/user.py` — 默认 handler 中调用 `CommandRouter` 附加 `intent_hint`
- `backend/app/core/context/plugins.py` — 扩展 `ContextPlugin` 可选 `is_needed(intent)` 门控
- `backend/app/core/context/schemas.py` — 增加 `metadata.intent_hint` 字段

### 评估产物（临时文件）

- `/tmp/opencode/supervisor_eval_results_full.json` — 初始基线
- `/tmp/opencode/supervisor_eval_results_after_tighten.json` — 移除工具 + 收紧 Prompt
- `/tmp/opencode/supervisor_eval_results_after_env_lean.json` — 补充环境信息
- `/tmp/opencode/eval_supervisor.py` — 评估脚本
- `/tmp/opencode/supervisor_eval_after_env_lean_run.log` — 最新运行日志

---

## 9. 总结

当前 Supervisor 已经走过了“去执行化”和“环境感知”两个阶段，但存在一个结构性隐患：**如果继续用全量上下文来满足更多场景，上下文会再次膨胀，走回老版的老路。**

本方案的核心是：

> **通过 L0 意图分类 + 按需复用现有 `ContextPlugin` 体系，让 Supervisor 的上下文变成“望远镜式”——只看当前问题需要看的东西。**

这不仅能解决当前环境/设备/宏边界问题，也为后续多轮、指代消解、更复杂的多 Agent 协作打下了可扩展的架构基础。
