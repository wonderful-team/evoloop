# 主动式 Todo 提醒机制评估报告

## 1. 方案概述
用户建议将“主动创建 Todo”的触发点放在 **Finish 节点**。即在 Agent 完成当前交互回合、准备向用户输出最终响应之前，对本次会话进行一次“后处理（Post-Processing）”分析，判断是否需要生成后续的待办提醒。

## 2. 合理性评估 (Viability Analysis)

### ✅ 为什么 Finish 节点是合适的？
1.  **全局视野 (Global Context)**:
    - Finish 节点位于工作流的末端，拥有本次交互的完整上下文（用户原始需求 -> 思考过程 -> 工具执行结果 -> 最终结论）。
    - 它可以判断任务是“彻底完成”了，还是“部分完成”，或者是“开启了一个长耗时进程”。
2.  **非侵入性 (Non-intrusive)**:
    - 将逻辑放在 Supervisor 或 Coder 中可能会干扰主要任务的决策路径（例如，Agent 可能会为了创建 Todo 而中断代码编写）。
    - 在 Finish 节点处理相当于“主要工作已交付，现在看看还有什么尾巴”，符合人类的工作习惯（回顾）。
3.  **兜底机制 (Catch-all)**:
    - 无论是 Supervisor 忽略了某个次要请求，还是 Executor 抛出了一个“等待中”的状态，Finish 节点作为最后一道关口，都有机会捕获。

### ⚠️ 潜在风险与挑战
1.  **延迟 (Latency)**:
    - 在返回响应给用户前增加一次 LLM 分析，会增加几秒钟的等待时间。
    - **对策**: 仅在检测到特定特征（如“wait”, "deploy", "later", "future"）或对话轮数较多时触发深入分析，或者使用流式输出先给用户响应，后台异步创建 Todo（需架构支持，目前架构可能是同步的，所以主要靠条件触发减少频率）。
2.  **过度打扰 (False Positives)**:
    - Agent 可能会把礼貌性的“回头见”误判为“待办事项”。
    - **对策**: Prompt 需严格限制，仅针对**具体、可执行且有时效性**的任务创建 Todo。

## 3. 场景覆盖 (Scenarios)

除了“长耗时任务”，我们在 Finish 节点还可以覆盖更多情境：

### 场景 A: 长耗时任务 (Long-Running Tasks) - *用户主要关注点*
*   **情境**: 用户让 Agent 运行测试脚本，Agent 调用终端工具，返回 "Tests started, pid 1234"。
*   **行为**: Finish 节点检测到 "started", "background", "pid" 等状态，创建一个 Todo: "Check test results (PID 1234) in 10 mins".

### 场景 B: 旁路/遗留任务 (Side-Quests / Unfinished Business)
*   **情境**: 用户说：“帮我修一下登录页的样式，顺便后面记得把数据库备份了。”
*   **行为**: Agent 专注于修样式（当前任务）。Finish 节点在回顾对话时，发现“数据库备份”这个意图未在本次工具调用中得到体现。
*   **动作**: 创建 Todo: "Backup database".

### 场景 C: 外部依赖/阻塞 (External Blockers)
*   **情境**: Agent 尝试部署，但发现缺少 API Key，回复用户：“我们需要 API Key 才能继续。”
*   **行为**: 这是一个“等待用户输入”的状态。
*   **动作**: 创建 Todo (可选): "Get API Key from user" 或提醒用户。 *(注：这种情况可能更适合由 Supervisor 保持在待定状态，但在无状态的 Agent 架构中，转为 Todo 是个好习惯)*

### 场景 D: 周期性/后续跟进 (Follow-ups)
*   **情境**: Agent 完成了功能开发，并建议：“建议24小时后观察一下内存泄漏情况。”
*   **行为**: 识别出建议中的时间约束。
*   **动作**: 创建 Todo: "Check memory usage for leaks" due in 24 hours.

## 4. 实施策略 (Implementation Strategy)

### 修改点: `app/core/engine/nodes/finish.py`

在 `finish_node` 函数中插入 `_check_proactive_todos` 步骤：

1.  **快速特征检测 (Heuristic Check)**:
    - 检查最近的 Tool Output 或 Final Response 是否包含关键词：`deploy`, `test`, `build`, `wait`, `minutes`, `later`, `tomorrow`.
    - 检查 User Message 是否包含 `also`, `and`, `later` 等暗示多任务的词。

2.  **LLM 分析 (LLM Analysis)**:
    - 如果特征匹配，调用轻量级 LLM (或复用当前 LLM) 进行抽取。
    - **Prompt**: "Review the implementation history. Did we start a long-running task? Did users mention side-tasks we ignored? If yes, output JSON for a new Todo."

3.  **工具调用 (Execution)**:
    - 如果 LLM 返回了 Todo 结构，在后台调用 `manage_todo`。
    - **静默 vs 显式**: 既然是 Finish 节点，建议将“已为您创建待办事项: [标题]”追加到最终回复的末尾，让用户通过。

## 5. 结论
在 `finish_node` 实现该逻辑在架构上是**最合理且风险最小**的方案。它能够有效地捕捉“长耗时”和“旁路”任务，显著提升 Agent 的体贴度和智能感。

建议按此方案推进。
