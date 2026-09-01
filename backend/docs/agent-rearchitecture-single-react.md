# Evoloop 彻底重构方案：单 Agent ReAct + Task 子代理（参考 OpenCode）

> 本文档与 `agent-rearchitecture-opencode.md` 的关系：后者是**渐进式收敛**（保留图引擎、只收敛行为），本文档是**彻底重构**（删除图引擎，改为 OpenCode 式「单 Agent ReAct + task 子代理」）。若实施本文档，图引擎代码整体移除。

## 0. 目标与度量

一条常规任务从：
- 现状：**3 次 LLM 调用 + 2 次状态摘要传递 + 节点间信息破坏**（Supervisor 决策 → ticket → Worker 执行 → Finish 审计）
- 目标：**1 次 LLM 调用（主 ReAct 循环）+ 0 次信息破坏**，子代理仅在需要隔离/并行时经 `task` 工具按需拉起。

**可量化目标（重构完成后的验收标准）**：

| 指标 | 现状 | 目标 |
|---|---|---|
| 常规任务 LLM 调用次数 | 3+（Supervisor/Worker/Finish） | **1**（主 ReAct 循环） |
| 节点间信息破坏 | 2 次（消息过滤 + 票摘要） | **0**（连续消息流） |
| 主 Agent 默认工具面 | supervisor 16 / worker 43 / finish 9 | **默认 15 个**（核心 12 + 特有 3；具身场景按需追加至 ≤18） |
| 工具注册与出池 | **102 个注册、55 个进池** | **102 保留注册**（供 `search_native_tools` 检索），**~30 进可用池**，**15 进默认面** |
| 工具命名 | 冗余后缀（execute_command/read_file/find_files…） | **对齐 OpenCode**（bash/read/glob/grep/edit/write/task/webfetch/websearch/todo/skill/question） |
| 提示词格式 | 76 个 `.j2`（Jinja2）+ `.md` | **全部 `.txt` 纯文本**（弃 Jinja2） |
| 一等公民 | Tool/Skill/MCP（Macro 混在工具池） | **Tool / Skill / MCP / Macro 四者并列** |
| 上下文管理 | 节点 filter 破坏 + LLM 主动 forget | 系统侧自动截断 + 窗口 + compaction |
| 防循环 | prompt 协议（unverifiable / verification_blocked_topics） | 代码层 doom_loop 检测 |

设计原则（取自 OpenCode）：

1. **一个 Agent，一套人格，一条连续消息流**——不再有 Supervisor/Worker/Finish 三种人格切换。
2. **默认路径只有一次 LLM**——用户消息 → 主 Agent ReAct → 直接输出。
3. **委派只在需要时发生**——像 OpenCode `task` 工具，可拆/需隔离上下文才 spawn 子代理。
4. **系统扛复杂度，模型只干活**——上下文裁剪、工具输出截断、防循环、错误恢复全部用确定性代码做。
5. **保留能力层**——记忆、学习、具身工具、HITL、事件、路由、沙箱都是资产，只换执行编排层。
6. **工具面最小化**——主 Agent 只暴露高价值 ~15 个工具；Skill/Macro/MCP 全走「索引 + 按需加载」，不让工具面膨胀（对齐 OpenCode 13 个内置工具）。

---

## 1. 目标架构

```
用户消息 (voice/web/mobile)
   │ dispatch_agent_run（不变）
   ▼
AgentSession（engine/session/）常驻多轮（保留，改内部）
   │ gate.wait_next()
   ▼
主 Agent ReAct 循环（重写 engine/loop.py）
   │ 一条连续消息流，主 Agent 拥有全量工具
   │  ├─ 主 ReAct：LLM → 工具执行 → 结果回灌 → 直到无 tool_calls
   │  └─ 需要时调 task 工具 spawn 子代理
   │        └─ 子代理 = 独立子会话（隔离上下文）
   ▼
最终输出（直接结束，无 Finish 审计节点）
```

### 与 OpenCode 的一一映射

| OpenCode | Evoloop 现状 | Evoloop 重构后 |
|---|---|---|
| `session/prompt.ts` `runLoop` | `engine/loop.py` `run_node_loop`（图循环） | **重写**：单 ReAct 主循环 |
| 主 Agent（`build`）直接拥有全工具 | Supervisor（无执行工具）+ Worker 两跳 | **合并**：主 Agent 直接全工具 |
| `tool/task.ts` spawn 子代理 | `SpawnSubagentsNode` + `AggregateSubagentsNode` + signals | **重写**：`task` 工具 |
| 子代理 `explore`/`general` 等 | `agent_config` 角色 + ticket | 子代理 = 命名 agent 定义（prompt/模型/工具） |
| 无 Finish 审计节点 | `FinishNode` + `AuditService` | **删除**（默认路径），审计降级为可选 `review` 子代理 |
| `context_trimmer.ts` + `truncate` + `compaction` | `context_trimmer.py`（已有） | **保留并加强**，删节点级 filter |
| `tool/registry.ts` 按权限过滤 | `ToolManager.get_node_tools` + RBAC | **保留**，收敛到单 Agent 全量池 |

---

## 2. 删除清单（减负核心）

| 模块 | 现状文件 | 处置 |
|---|---|---|
| 图节点 | `engine/nodes/{supervisor,worker,finish,sequential_workflow,spawn_subagents,aggregate_subagents}.py` | 删除；sequential_workflow 改工具；spawn/aggregate 改 `task` 工具 |
| 信号间接层 | `engine/signals/signals.py`（RouteToSignal/SpawnSubagentsSignal/拦截器） | 删除 `route_to` 拦截→信号机制；直接工具调用 |
| 路由切换 | `engine/routers.py` `RoutingTarget` | 删除（主循环不需要 next_node 状态机） |
| 执行票 | `engine/state/config.py` `ExecutionTicket` | 删除（主 Agent 无需"票"派活）；其承载的字段分流：`mcp_servers_required`/`agent_config.tools` -> **`task` 工具参数** + 会话上下文（`EvoContext`），`acceptance_criteria`/`focus_paths` -> `task` 工具参数（传给子代理） |
| 消息过滤 | `supervisor._filter_messages_for_supervisor`、`worker._build_worker_view` | 删除（信息破坏源） |
| 审计节点 | `finish.py` + `AuditService` 默认路径 | 删除默认审计；改为可选 `review` 子代理 |
| 反循环协议 | `verification_blocked_topics` / `report_outcome` / prompt 防呆规则 | 删除（代码层 doom_loop 检测替代） |
| 工具池爆炸 | `agent_main.yaml` worker 40+ 工具 | 收敛到主 Agent 单池（MCP 渐进披露保留） |

---

## 3. 新主循环设计（`engine/loop.py` 重写）

```
async def run_agent_loop(state, config, *, thread_id, max_steps=30):
    system = build_system_prompt(state, config)   # 主 Agent 人格 + 环境块 + skills 索引 + 记忆
    messages = load_full_history(state)           # 完整消息流，不过滤
    while step < max_steps:
        messages = trim_context(messages)         # ContextTrimmer（确定性）
        response = llm.stream(system, messages, tools)
        if not response.tool_calls: break         # 纯文本 → 结束
        for tc in response.tool_calls:
            if tc.name == "task":                 # 子代理：隔离子会话
                result = await spawn_subagent(tc)
            else:
                result = await execute_tool(tc)   # AgentToolExecutor（保留）
            messages += result
        if doom_loop_detected(messages): ask_user()  # 代码层防循环
    return last_response
```

要点：
- `max_steps` 提到 **30**（现状 Supervisor 仅 3-5，长任务必须靠多次 LLM 决策--这正是 OpenCode 单循环优势）。
- 主 Agent 拥有全量工具（合并 supervisor+worker 池），按任务用 MCP 渐进披露收敛注入。
- 上下文统一 `ContextTrimmer`，删节点级 filter；工具输出写回前 token 级截断 + 摘要。
- 结束条件 = 无 tool_calls 的文本回复（OpenCode 语义），无 Finish 审计 LLM 调用。

### 3.5 运行中新消息语义（steer / queue / interrupt）

> 现状 Evoloop 有 parent-run-liveness 设计（Worker rollout 期间会话可接新消息）；OpenCode V2 有明确的 steer/queue/promote 语义。单 ReAct 主循环是长驻阻塞循环，**必须定义新消息到达时的行为契约**，否则多通道（web/voice/mobile）行为回归。

主循环每步（LLM 调用前、工具执行前）检查 `gate.poll_nonblocking()`：

| 场景 | 语义 | 行为 |
|---|---|---|
| 主循环**空闲**（上轮已结束） | **queue** | `user_message` 事件正常触发新一轮 delivery（现状不变） |
| 主循环**运行中**，新消息与当前任务**相关**（补充信息/改需求） | **steer** | 新 user 消息直接 append 进 `messages`，当前步工具结果回灌后，下一步 LLM 调用即看到；重置 `max_steps` 剩余额度（对齐 OpenCode「promote any new user input resets provider-turn allowance」） |
| 主循环**运行中**，新消息与当前任务**无关**（新任务） | **queue** | 挂到 `gate` 队列，当前轮跑完（END）后作为下一轮 delivery 消费；activity monitor 显示"排队中" |
| 用户**停止/取消** | **interrupt** | `session_cancel` -> `activity_monitor.stop_run` -> 协作式检查点取消（保留现状 `check_cancellation` 机制） |

- steer/queue 判定：默认 **steer**（OpenCode 语义：新输入视为对当前工作的补充）；仅当当前轮 `steps > N` 且用户消息以明确新指令开头时降级 queue（可配置，v1 可全部 steer）。
- 语音通道复用同一语义：voice 的中途插话 = steer。
- **不保留** parent-run-liveness 的 rollout 后台化（那是图架构的 Worker 产物；单 ReAct 中主循环即执行体，steer/queue 已覆盖其场景）。

### 3.6 HITL 挂起与恢复（工具中断 -> 会话挂起 -> 续跑）

> 现状：HITL 工具抛 `AgentHumanInterruptException` -> 会话 `_hang_for_resume` 挂起 -> resume 重建 state 续跑。单 ReAct 循环里必须保证**中断不丢执行现场**。

设计（复用现有 HITL 双轨，只改恢复宿主）：

1. **中断点**：`question` / approval / 授权门控工具在 executor 内抛 `AgentHumanInterruptException`。主循环捕获后：
   - **消息持久化先行**：当前未闭合的 assistant(tool_calls) 与已完成的 tool 结果已由 `DatabaseCallbackHandler` 流式落库（现状已有）；
   - 在 DB `human_requests` 登记 + 推送前端（现状 `HITLOrchestrator` 不变）；
   - 主循环**退出**（不 busy-wait），`AgentSession` 状态置 `awaiting_hitl`，`ContextManager.save`。
2. **恢复点**：用户答复经 `session_manager.submit(is_resume=True)` -> 会话重建：**从 DB 加载完整消息流**（`runner_base.build_agent_state` 已具备）+ 未闭合 tool_call 的 tool 结果回填（`resume_and_persist` 现状机制，HITL 答案写入原 tool 消息）-> 重进 `run_agent_loop`，从"有未闭合 tool_calls 的最后一步"续跑。
3. **不变式**：恢复后的 `messages` 与中断前逐条一致（HITL 答案替换占位 tool 结果），模型无感知中断发生。
4. **超时/取消**：`hitl_cancel` -> 按 REJECTED 续跑（现状 normalize 语义不变）。

> 关键差异 vs 现状：不再需要 `_reload_worker_state`/worker rollout 特化路径--单 ReAct 的恢复就是"重放消息流"，与 OpenCode `resume_graph_background` 同构。

### 3.7 会话收尾管线（记忆提取 / 宏学习触发迁移）

> 现状记忆自动采集链路：`AuditService` -> `EXTRACTION_REQUESTED` 事件 -> `MemoryLifecycleSubscriber` 落 `MemoryEntry`；宏创建资格由 `FinishNode` 标记。删除 Finish/AuditService 默认路径后，**两个学习闭环的触发点必须迁移**，否则静默断链。

迁移设计（全部改挂在** run 收尾事件**上，代码层触发，无 prompt 规则）：

| 现状触发 | 迁移后触发 |
|---|---|
| `AuditService.execute` -> `EXTRACTION_REQUESTED` -> 记忆提取 | 主循环 END 时发布 `SESSION_COMPLETED`（现状已有该事件）-> 新增 `MemoryExtractionSubscriber` 订阅：异步提取本轮 episodic/concept 写入 `MemoryManager`（fire-and-forget，不阻塞收尾） |
| `FinishNode` 标记 `macro_creation_eligible` -> `MacroCreatorService` | `SESSION_COMPLETED` 订阅者做同样判定（replayable 确定性步骤检查，`MacroCreatorService.is_eligible` 复用）-> 触发自动宏创建 |
| `finish.prompt.j2` 的 `create_skill_from_session` 指令（skill 提炼） | 改为 `SESSION_COMPLETED` 订阅：会话含非平凡可复用解题路径时生成 candidate skill（pending_review，不自动激活，语义不变） |

- 收尾管线统一放 `engine/react/completion.py`，顺序：`SESSION_COMPLETED` 发布 -> 记忆提取 -> 宏资格判定 -> skill 候选生成（三者并发、互不阻塞、失败仅告警）。
- 原 `AuditService`/`FinishNode` 代码在阶段 B 删除时，其提取逻辑函数迁移进各 Subscriber。

---

## 4. Task 子代理设计（替代 Spawn/Aggregate）

参照 OpenCode `tool/task.ts` + `agent/agent.ts`。

### 4.1 新目录 `engine/subagent/`

```
engine/subagent/
├── definitions.py   # 内置子代理：explore / general / reviewer / researcher
├── spawner.py       # 创建子会话 + 权限继承
├── task_tool.py     # task 工具（主 Agent 调用入口）
└── result.py        # 子代理返回文本聚合
```

### 4.2 `task` 工具参数（与 OpenCode 一致）

```
{ subagent_type: str, description: str, prompt: str }
```

- 子代理 = 独立 AgentState + 独立消息流 + 独立 prompt（`explore.txt` 等），**看不到父会话消息**（隔离上下文，OpenCode 语义）。
- **权限继承**（参照 OpenCode `agent/subagent-permissions.ts`）：子会话继承父会话 deny/external_directory 规则，子代理自身权限决定能力；默认禁子代理再 spawn task（防递归，`subagent_depth` 限制）。
- **聚合**：OpenCode 语义是「每个子代理返回一条最终消息给父 Agent」，父 Agent 自己合并，无需 `AggregateSubagentsNode` + LLM 聚合轮。
- **并行**：主 Agent 一条消息里发多个 task 调用 → 子代理并行跑，结果各自回灌 → 主 Agent 继续。
- **内置子代理**（映射 OpenCode）：
  - `explore`：文件搜索，只读工具，`explore.txt`（原 explore.txt 转纯文本）
  - `general`：通用并行子任务
  - `reviewer`：替代 Finish 审计（用户要求 review 时 spawn，只读只审计不改码）

### 4.3 A2A 远程委派（`task` 工具的 `remote` 语义）

> 现状 `send_agent_task`/`list_agents` 是独立工具，且 A2A 是**挂起等远端回调**语义（awaiting_a2a），与本地子代理同步等结果不同。合并进 `task` 工具时必须区分两种模式。

`task` 工具参数扩展：

```
{ subagent_type, description, prompt,
  remote?: { agent_id: str }        # 省略 = 本地子代理；给出 = A2A 远程设备
}
```

- **本地模式**：spawn 子会话，同步（并行）等结果回灌（§4.2 语义）。
- **remote 模式**（A2A）：
  1. 调用方（主 Agent 或子代理）经 `task(remote={agent_id})` 发送远端任务，得到 `task_id`；
  2. `task` 工具**返回"挂起占位"**（`[A2A task dispatched: task_id, awaiting callback]`），主循环当前步结束、会话置 `awaiting_a2a`（与 §3.6 HITL 挂起同构的挂起-恢复机制）；
  3. 远端回调（`a2a_callback` 经 `EngineCommandSubscriber`，现状已有）把结果写入对应 tool 消息 -> `session_manager.submit(is_resume=True, kind="a2a_result")` 唤醒；
  4. 恢复 = 重放消息流（§3.6 不变式），主 Agent 带着远端结果继续。
- **need_input**：远端要求用户输入时转 `question`（现状 pending_need_inputs 语义保留，转为一问一答后 resume 远端）。
- `list_agents` 并入 `task` 工具描述（可用远端设备列表注入动态索引 `<available_agents>`，同四等公民索引模式）。

### 4.4 多技能串行工作流（SequentialWorkflow 的去节点化）

> 现状 `SequentialWorkflowNode` 承载"多 skill 顺序执行 + 步间上下文传递"。单 ReAct 中不再需要专用节点：

- **主 Agent 顺序调 `skill(name_1)` -> 执行 -> `skill(name_2)` -> 执行**：SKILL.md 正文就在消息流里，步间上下文天然连续（这正是单消息流的优势，无需 workflow_step_index 状态机）。
- 长 SOP（>3 步）用 `plan` 工具落 DB 计划（现状 Plan/PlanStep 保留），主 Agent 按计划逐步推进，每步完成调 `plan` 更新状态（前端面板语义不变）。
- 原 `workflow_plan`/`workflow_step_index`/`workflow_results` state 字段随阶段 B 删除。
- 唯一保留特化：**值守巡检等多 skill 固定流水线**由调度器（AutonomousTask）逐条发消息驱动，天然逐轮执行，无需图节点。

---

## 5. SKILL 在单 ReAct 的实现（OpenCode 机制分析）

OpenCode 的 SKILL 是「**索引注入 + 按需加载**」两段式，而不是把全部技能内容塞进 system prompt。这是它不爆上下文、且技能始终准确的关键。

### 5.1 发现与注册（`packages/opencode/src/skill/index.ts`）

- 扫描来源：项目 `skill/`、`skills/`、`~/.claude/skills/`、`~/.agents/skills/`、配置 `skills.paths`、远程 `skills.urls`（经 `skill/discovery.ts` 从 index.json 下载 SKILL.md 到缓存）。
- 每个 skill = 一个目录下的 `SKILL.md`，frontmatter 解析出 `name` + `description`，正文为指令（`index.ts:37-43` Info schema）。
- `available(agent)` 按权限过滤（`index.ts:310-315`）。
- `fmt(list, {verbose})` 生成注入 system prompt 的 `<available_skills>` 列表（`index.ts:321-346`）。

### 5.2 索引注入 system prompt（`session/system.ts:105-117`）

```ts
skills: (agent) => [
  "Skills provide specialized instructions and workflows for specific tasks.",
  "Use the skill tool to load a skill when a task matches its description.",
  Skill.fmt(list, { verbose: true }),   // 只含 name + description + location，无正文
].join("\n")
```

关键：**system prompt 里只放技能目录（name/description，少量 token）**，模型据此判断「该调哪个 skill」。

### 5.3 按需加载（`tool/skill.ts`）

- `skill` 工具参数只有 `{ name }`（`skill.ts:8-10`）。
- 执行时：`skill.require(name)` → 权限 `ctx.ask({permission: "skill", ...})` → ripgrep 采样同目录文件列表（`!**/SKILL.md`，limit 10）→ 返回完整 SKILL.md 正文 + 基础目录 + 文件列表：

```ts
output: [
  `<skill_content name="${info.name}">`,
  `# Skill: ${info.name}`,
  info.content.trim(),                          // 完整 SKILL.md
  `Base directory for this skill: ${base}`,
  "Relative paths in this skill are relative to this base directory.",
  "<skill_files>", ...files..., "</skill_files>",
].join("\n")
```

- 工具描述（`tool/skill.txt`）：
  > Load a specialized skill when the task at hand matches one of the skills listed in the system prompt.

### 5.4 在单 ReAct 中的完整闭环

1. **system prompt 注入索引**（5.2）——模型知道有哪些技能及一句话用途，token 开销极小。
2. **模型按需调用 `skill(name)`**——当任务匹配某技能描述时，工具返回**完整 SKILL.md 正文**作为普通 tool result 进入当前消息流。
3. **内容即上下文**——加载后的 SKILL.md 就是一条普通工具结果，模型据此行动；脚本/参考文件通过 `<skill_files>` 中的路径用 `read` 读取。
4. **权限门控**——每次加载过 `Permission` 的 `skill` 规则。

**结论**：SKILL 不改变 ReAct 架构，只是「目录在 system、正文按需进消息流」。模型永远只付「索引」的固定 token，技能正文按需付费。

### 5.5 Evoloop 现状差距

| OpenCode | Evoloop 现状 | 重构后 |
|---|---|---|
| system 只放技能索引（name+description） | `skill_block.txt` 全量注入 active SOP 正文 + `supervisor_context_ticket.txt` 注入可用技能目录 | system 只放索引 |
| `skill` 工具按需加载完整 SKILL.md | 无 `skill` 工具；`get_skill` 工具需 LLM 猜名（`list_skills` 另注入） | 新增 `skill` 工具（同 OpenCode） |
| 加载后的正文即普通 tool result | SOP 以 knowledge_blocks 全量附加到 mission ticket | 正文作为 tool result 进入消息流 |

### 5.6 Evoloop 落地方案

1. **新增 `engine/subagent/` 旁的能力目录 `engine/skills/`**：
   - `manager.py`：扫描 `~/.evoloop/skills` + 项目 `skills/` + DB 中的 `LearnedSkill`，构建 name→(content, dir, description) 索引。
   - `tool.py`：`skill(name)` 工具——`require(name)` → 权限检查 → 返回 SKILL.md 正文 + 基础目录 + 资源文件列表（复用 `skills/lifecycle.py` 的存储与 `SkillResolver`）。
2. **修改 system prompt 组装**：主 Agent 的 `main.txt` 只注入 `<available_skills>`（name+description，截断描述到一句话），删除 `worker_mission_ticket.txt` 的 knowledge_blocks 全量注入。
3. **权限**：`skill` 工具走 `Permission`（`is_hidden`/`required_benefit` 语义保留）。
4. **技能正文路径**：`skill` 工具正文输出到消息流；脚本/模板经 `<skill_files>` 路径用 `read_file`/`execute_command` 读取执行。

### 5.7 Macro 是 Evoloop 独有的一等公民（与 MCP/SKILL/TOOL 并列）

> ⚠ 关键认知：OpenCode 里 **MCP / SKILL / TOOL 是一等公民**。Evoloop 在此基础上**多一个 Macro**——它同样是**一等公民**，不是 Tool 的附属。重构方案必须把 Macro 与 Skill 平级对待：**Skill = 指令/SOP（提示层）**，**Macro = 可回放确定性脚本（执行层）**，两者互相独立、并列注册、并列注入。

#### 5.7.1 Macro 现状（Evoloop 独有资产，保留）

- **定义与生命周期**：`app/core/learning/macro/`（`compiler.py` Trace→MacroScript、`creator.py` 自动创建、`lifecycle.py`、`service.py`、`runner.py`、`engine/` 执行引擎、`healing_policy.py` 自愈）。
- **工具**：`learning/macro/tools/`（`run_macro` / `list_macros` / `read_macro` / `create_macro` / `update_macro` / `delete_macro`）。
- **执行策略**：`WEB_POLICY`（自愈回退 agentic 恢复）/ `VOICE_POLICY`（快速失败 + 仅桌面源），`MacroService.run_deterministic` 统一入口。
- **自动创建**：`FinishNode` 标记 `macro_creation_eligible` → `MacroCreatorService`（`settings.AUTO_MACRO_CREATION_ENABLED` 门控）。
- **提示词关联**：AGENTS.md 提到 `macro_usage.j2` 曾加入"宏只返回 completed、无验证手段时停止"的反循环规则——该规则随重构删除（防循环移入代码层）。

#### 5.7.2 与 SKILL 并列的一等公民设计（对齐 OpenCode 索引+按需加载）

| 维度 | SKILL（指令/SOP） | MACRO（确定性脚本） |
|---|---|---|
| 本质 | 指令/工作流说明（提示层） | 可回放动作序列（执行层） |
| 索引注入 | `<available_skills>`（name+description） | `<available_macros>`（name+description） |
| 按需加载 | `skill(name)` 工具返回 SKILL.md 正文 | `read_macro` / `macro(name)` 工具返回 MacroScript 步骤 |
| 执行 | 模型读正文后自行行动 | `run_macro(macro_id/name)` 确定性回放 |
| 生命周期 | `skills/lifecycle.py`（pending_review→verified） | `macro/lifecycle.py`（自动创建→校验→激活） |
| 权限 | `skill` 权限规则 | `run_macro` 走 HITL/`required_benefit`（已有） |
| 路由 | L0/L1 意图可命中 | L0 本地毫秒级执行（voice） |

#### 5.7.3 落地方案

1. **索引注入**：`main.txt` 动态块同时注入 `<available_skills>` 与 `<available_macros>`（各截 name+description，`context_hydrator` 已有 `list_active_macro_index` 可复用）。
2. **按需加载工具**：新增 `macro(name)` 工具（对齐 `skill(name)`）——`require(name)` → 权限 → 返回 MacroScript 步骤概览 + 参数说明；实际执行仍走 `run_macro`。
3. **统一治理**：Macro 与 Tool/Skill/MCP 同走 `@evoloop_tool` 注册 → `ToolManager` 按节点收敛注入；`run_macro`/`list_macros` 在主 Agent 工具池保留，但**不**塞进 system 正文。
4. **执行收敛**：`run_macro` 默认确定性执行；失败时按 `WEB_POLICY` 自愈回退 agentic（保留），不因重构删掉 Macro 能力。
5. **学习闭环**：主 Agent 完成任务后，仍可由系统侧（代码层，非 prompt 规则）评估 `macro_creation_eligible` 并触发自动宏创建。

#### 5.7.4 与 OpenCode 对照（四等公民）

| OpenCode 一等公民 | Evoloop 一等公民（重构后） | 提示词形态 | 调用方式 |
|---|---|---|---|
| Tool | Tool（@evoloop_tool） | 工具描述（schema） | 直接工具调用 |
| Skill | Skill（SKILL.md / SOP） | `<available_skills>` 索引 | `skill(name)` 按需加载 |
| MCP | MCP server | `<available_mcp>` 索引 + `<mcp_instructions>` | MCP 工具直接调用 |
| — | **Macro（独有）** | `<available_macros>` 索引 | `macro(name)` 加载 + `run_macro` 执行 |

> **结论**：重构后 Evoloop 有**四类**一等公民：Tool / Skill / MCP / Macro。它们统一走「system 只放索引 + 按需加载/执行 + 权限治理」模式，Macro 与 Skill 平级、与 OpenCode 的 Skill 同等地位（OpenCode 无对应物，是 Evoloop 差异化能力）。

---

## 6. 上下文管理强化（OpenCode 移植）

现状 `context_trimmer.py` 已具备分层窗口 + token 预算，缺三件事：

1. **工具输出自动截断**：`AgentToolExecutor.execute_tool` 写回前，超预算 tool output 自动折叠为摘要 + 存文件，附 `[TRUNCATED: see file://...]`（OpenCode `truncate` 语义）。**删除 prompt 中 "call forget_tool_outputs" 指令**（原 `worker.txt:46` 规则移入代码层自动管理）。
2. **删除节点级 filter**：`supervisor._filter_*`、`worker._build_worker_view` 直接删。
3. **Compaction**：保留现有自动压缩（消息超阈值 → 结构化总结，参考 OpenCode `agent/prompt/compaction.txt`），主循环内触发，模型无感知。

---

## 7. 系统提示词收敛（单 Agent 人格）

**新建 `templates/core/agent/main.txt`**（替代 supervisor/worker/finish 三套，纯文本无模板）：

```
你是用户的唯一助手。
## 语言 / 简洁 / 输出格式
## 工具使用
- 直接使用工具完成任务，不要只描述。
- 文件操作用专用工具；bash 只用于真实系统命令。
- 多工具并行调用；有依赖时串行。
- 复杂可拆任务 → 用 task 工具 spawn explore/general 子代理（给出完整上下文）。
## 环境（环境块 / 工作目录 / 平台 / 日期）
## 技能索引（<available_skills>，仅 name+description）
## 记忆（热记忆摘要，冷记忆按需 recall）
## 安全规则（保留具身安全：不删 .git / 不 DROP 生产库 / 密钥不泄露）
```

- 不再有「Supervisor 无执行工具」「Worker 不对用户说话」「Finish 只验收不监督」等人格税。
- 每个子代理一份简短 prompt（`explore`/`reviewer`）。
- 动态块（记忆/技能/环境/计划）经 context ticket 思路注入但收敛体量（几百字符）。

### 7.1 通道变体（duty / voice）

> 现状 worker.prompt.j2 的 duty 段（1500 字硬限、直接回复客户）与 finish 的 `<evoloop_tts_summary>` 语音摘要，在三套 prompt 删除后必须有新宿主。

采用「基础 prompt + 通道追加段」（对齐 OpenCode 模型变体思路，代码层按 `EvoContext.metadata.source` 条件拼接）：

| 通道 | 追加文件 | 内容 |
|---|---|---|
| 默认（web） | 无追加 | `main.txt` 原样 |
| `duty`（值守客服） | `main.duty.txt` | "你的最终回复直接送达客户：硬限 1500 字符（~750 汉字）；只输出结论与关键摘要；禁止明细列表/表格/SQL/代码块/过程细节" |
| `voice`（语音） | `main.voice.txt` | "你的回复将由 TTS 播报：无 markdown/列表/表格/emoji；先一句安抚再委派；复杂问题一句话收尾"（原 supervisor voice 段语义迁移） |

- **TTS 摘要**：语音通道收尾时（§3.7 收尾管线）由一次**轻量 LLM 调用**（small model，现状 `title` 生成同款机制）从最终回复生成 `tts_summary`，填入 `SessionCompletedData.tts_summary` 字段--替代原 `<evoloop_tts_summary>` XML 结构，**主回复不再承担双格式输出**。
- 拼接位置：`main.txt` 尾部（`system` 数组 append，对齐 OpenCode `is_voice` 条件段）。

---

## 8. 分阶段实施（风险可控）

### 阶段 A：并行新主循环（不动旧图，可回滚）
**A.0 前置（先于一切，防上下文爆窗）**：executor 层**统一截断先行**--`AgentToolExecutor.execute_tool` 写回前超预算 tool output 自动折叠+存文件+路径回填（§6.1）。**原因**：旧图节点过滤虽破坏信息但客观上控窗，删掉它之前必须有替代，否则阶段 A 切全量消息流 + `max_steps=30` 就会爆上下文。

1. 新建 `engine/react/`（loop.py + subagent/ + skills/ + completion.py），写 `run_agent_loop`，复用 `ContextTrimmer` / `AgentToolExecutor` / `EvoMessageConverter`。
2. `agent_main.yaml` 加 `agent_mode: "react" | "graph"`（默认 `graph`，新模式灰度开关）；同时**收敛主 Agent 工具池到默认 15 个**（§10.2.1），作为 react 模式默认工具面。
3. 写 `main.txt` + `main.duty.txt`/`main.voice.txt` + explore/reviewer 子代理 prompt（`.txt`）+ `skill` 工具 + `macro(name)` 工具。
4. 建 `task` 工具（不依赖 signals，直接 spawn 子会话；含 §4.3 remote/A2A 语义、§3.6 挂起恢复接口）。
5. **收尾管线**：`completion.py` 接 `SESSION_COMPLETED` -> 记忆提取 / 宏资格 / skill 候选（§3.7），先于删除 AuditService 落地，保学习闭环不断链。

### 阶段 B：切默认 + 删图
1. `session.py` `_run_turn` 从 `run_node_loop` 切到 `run_agent_loop`；`background_agent/runner.py` 单发路径合并到同一 loop（N8）。
2. 删除 `nodes/` 图节点、`signals`、`routers.py` 状态机、`ExecutionTicket`、节点级 filter。
3. `dispatch.py` / `runner_base.py` / `context_hydrator.py` 适配单状态。
4. 移除 `finish.py` 默认审计路径（`needs_audit` 一律 false；review 走 `reviewer` 子代理）；其记忆/宏触发逻辑已在 A.5 迁移至 completion.py。

### 阶段 C：上下文与提示词收敛
1. 工具输出自动截断全量启用（A.0 已下沉 executor，本阶段做 compaction 与窗口调优）。
2. 删 prompt 中 forget_tool_outputs / 反循环 / unverifiable 规则，靠代码层 doom_loop 检测。
3. `main.txt` 收敛动态块体量（记忆截 300 字符、技能/宏索引截断）。

### 阶段 D：回归与指标
- **度量埋点前置（阶段 A 就加）**：`AgentActivity` 增加字段 `llm_calls`、`input_tokens`、`output_tokens`、`tool_errors`（每 run 汇总）；作为 §0 量化目标（3→1 跳、token 降幅）的验收依据。
- **测试影响清单**：删图引擎前先盘点 `tests/unit/core/engine/`（nodes/signals/routers/state 相关用例）、`tests/integration/`（宏工具）、`tests/e2e/` 中引用旧工具名/图流程的用例，逐条迁移到新名与单循环语义；`test_prompt_templates.py` 同步 `.txt` 化。
- 对比：同任务 LLM 调用次数（3→1）、tokens 总量、完成率、平均延迟、**工具误选率**（新增埋点）。
- `tests/e2e` 全量回归 + 语音/值守通道专项回归（§7.1 变体）。

---

## 9. 保留不动（能力资产）

- `tools/`（@evoloop_tool 注册/执行/hook/diff）——只收敛池子
- `memory/`（三层 + ToolOutputMemory + Dream）
- `learning/`（skill/macro 合成 + 宏引擎）——**Macro 是一等公民**（与 Tool/Skill/MCP 并列），主 Agent 可经 `macro(name)` 加载 + `run_macro` 执行
- `hitl/`、`events/`、`routing/`（L0/L1）、`atlas/`、`execution/sandbox + terminal`、`infrastructure/llm`
- `context_hydrator.py` 的望远镜加载 + intent 门控（收益明确，保留）

---

## 10. 提示词 / 工具 / MCP 全面对齐 OpenCode

除执行架构外，OpenCode 的**提示词组装**、**工具定义与执行**、**MCP 集成**三套机制也值得逐一对齐——它们共同决定了「模型看到的输入质量」。以下为 OpenCode 实现剖析 + Evoloop 对齐方案。

### 10.0 提示词格式约定：纯 `.txt` 静态文本（弃用 `.j2` / `.md`）

**OpenCode 的做法**：所有提示词是**纯文本 `.txt` 文件**（`anthropic.txt`、`default.txt`、`gemini.txt`、`skill.txt`、`task.txt`…），构建时由打包器直接 import 成字符串常量（如 `import PROMPT_DEFAULT from "./prompt/default.txt"`），**没有模板引擎、没有占位符语法**。动态内容一律在**代码层**拼接（`system.ts` / `request.ts` 用数组 `join`），个别按需替换用字符串 `replaceAll`（如 `PROMPT_META.replaceAll("{{MODEL_NAME}}", name)`）。

**Evoloop 现状**：`app/config/templates/` 下 76 个 `.j2`（Jinja2 模板，含 `{% if %}` / `{% include %}` / 过滤器）+ 个别 `.md`，靠 `app/utils/template.py` 的 Jinja2 Environment 渲染。

**对齐方案**：提示词文件**全部改为 `.txt`**，废弃 Jinja2：

1. **文件格式**：`.j2`/`.md` → `.txt`（例如 `main.prompt.txt`、`supervisor.txt`、`worker.txt`、`explore.txt`、`reviewer.txt`、`skill.txt`）。
2. **静态内容**：所有"你是谁 / 决策规则 / 工具使用 / 安全规则 / 输出格式"写死进 `.txt`，无模板变量。
3. **动态内容移入代码**：
   - 环境块 / 记忆摘要 / 技能索引 / 计划状态 → 由 `context_hydrator` / prompt builder 用 Python 字符串**组装**后，作为 `<system-reminder>` 或 user 消息注入（对齐 OpenCode `system.ts`）。
   - 需要占位的（如 `{{ user_lang }}`、`{{ role_name }}`）→ 代码层 `str.replace` 逐占位符替换。**禁用 `str.format`/f-string 渲染模板**：提示词正文必然含 JSON/代码示例的花括号，`str.format` 会抛 KeyError；只用「文件读取 + 显式占位符表替换」。
4. **读取方式**：新增 `PromptLoader`（`app/utils/prompt_loader.py`）——纯文件读取 + 占位符表替换（非 Jinja2、非 format），替换 `render_template`（Jinja2）。保留 `render_template` 作为兼容壳（内部转发到 loader），逐步迁移。
5. **include/fragment 拆解**：`{% include '...j2' %}` 在代码层用「基础 txt + 条件追加片段字符串」表达（对齐 OpenCode `system` 数组按条件 push）。
6. **测试**：`tests/unit/core/test_prompt_templates.py` 改为校验 `.txt` 存在 + 渲染（纯替换）无残留 `{{ }}`。
7. **分层迁移**（76 个 `.j2` 不必一刀切）：
   - **一期（随本重构）**：`core/engine/` 与 `core/agent/` 下的 Agent 提示词（supervisor/worker/finish/fragments/ticket ~25 个）--它们被新架构直接替代，天然消失或转 `.txt`；
   - **二期（重构后独立做）**：`memory/`、`learning/`、`vision/`、`domain/` 的**内部合成 prompt**（记忆蒸馏/skill 合成/多模态格式化 ~50 个）--它们不进 Agent 消息流，收益低、量大，保留 Jinja2 至二期，由 `render_template` 兼容壳继续服务。

> 收益：提示词无模板逻辑、可被模型直接读懂；渲染零依赖、零模板语法错误；与 OpenCode 完全同构，便于后续直接搬运/对比。

---

### 10.1 提示词组装（OpenCode `session/llm/request.ts` + `session/system.ts`）

**OpenCode 的组装是"静态分层 + 动态按需"**，最终 system 由三层拼接（`llm/request.ts:58-66`）：

```
system = agent.prompt ?? SystemPrompt.provider(model)   # ① 模型专属静态提示词（95~155 行）
       + input.system                                    # ② env + instructions + mcp + skills
       + user.system                                     # ③ 用户显式 system
```

- **① 静态层**：按模型路由到 12 个 `.txt`（`system.ts:27-49` 的 `provider()`：claude→anthropic.txt、gpt→gpt.txt、gemini→gemini.txt、kimi→kimi.txt、默认 default.txt）。只描述"你是谁 + 工具使用 + 风格 + 代码引用格式"，**不含任何任务/记忆/技能正文**。Evoloop 侧：模型无关通用部分（`main.txt`）+ 可选模型变体（`anthropic.txt`/`gpt.txt`/`gemini.txt`/`kimi.txt`），由 `prompt_loader.provider(model)` 选择。
- **② 动态层**（`system.ts`）：
  - `environment()`：仅 6 行 `<env>`（模型名/工作目录/git/平台/日期）＋ 可选 `<available_references>`（`system.ts:67-103`）
  - `instructions()`：`AGENTS.md` / `CLAUDE.md` / `config.instructions`（`instruction.ts`，只挂路径+内容，按需 `findUp`）
  - `mcp()`：仅当有 connected 服务器且工具未被权限禁用时注入 `<mcp_instructions>`（`system.ts:119-135`）
  - `skills()`：只注入 `<available_skills>` 索引（name+description，`index.ts fmt`）
- **③ 用户层**：`PromptInput.system` 用户显式指定。
- **运行时注入**：`SessionReminders`（plan 模式提醒）、`MAX_STEPS_PROMPT`、结构化输出提示，均为**小块 `<system-reminder>`**。

**对齐方案（Evoloop）**：
1. 新 `main.txt` 只承担「①静态层 + 少量环境」，删掉 `supervisor/worker/finish` 三套 + 海量 fragment 全量注入。
2. 动态层按需：环境块 6 行；`AGENTS.md` 用 `Instruction` 同款 findUp 挂载；技能只注入索引；记忆热记忆截 300 字符、冷记忆 `recall`。
3. 运行时只注入 `<system-reminder>` 小块（plan 提醒 / max_steps / HITL），不注入大块 ticket。
4. 保留 `intent_hint` 望远镜门控（`context_hydrator.py`）——这是 Evoloop 相对 OpenCode 的增强，保留。

---

### 10.2 工具定义与执行（OpenCode `tool/tool.ts` + `tool/registry.ts` + `session/tools.ts`）

**OpenCode 的工具契约（`tool/tool.ts`）**：

```ts
export interface Def<Parameters, M> {
  id: string                       // 工具名
  description: string              // 描述（含 Usage notes，如 task.txt）
  parameters: Schema.Decoder       // 参数 zod schema
  execute(args, ctx): Effect<ExecuteResult>  // 返回 { title, metadata, output, attachments }
  formatValidationError?(err)      // 参数校验失败 → 模型可读提示
}
export interface Context {
  sessionID, messageID, agent, abort, callID,
  messages,                         // 当前完整消息流
  metadata({title, metadata}),      // 流式更新工具状态（title/进度）
  ask(permissionRequest),           // 权限询问
}
```

**关键特性**：
1. **Schema 校验 + 错误回喂**：`Tool.define` 包装器（`tool.ts:99-149`）编译参数 schema，LLM 调用参数不合法 → `InvalidArgumentsError`（`tool.ts:24-34`）→ 作为 tool result 回喂模型要求"rewrite the input"。这是 OpenCode 模型极少参数错误的根本原因——**系统侧校验，模型侧自纠**。
2. **统一截断**：每个工具 `execute` 后自动过 `truncate.output`（`tool.ts:135`），超限 → 摘要 + 写文件 + `outputPath` 回填。**工具作者不需要关心截断**。
3. **上下文注入**：每个工具拿到 `ctx.messages`（完整消息流），可自行读取/分析历史，无需全局黑板。
4. **执行时权限**：`ctx.ask({permission})` 统一权限询问（`session/tools.ts:59-90`）。
5. **执行前/后钩子**：`tool.execute.before` / `tool.execute.after` 插件触发点（`session/tools.ts:106-130`）。
6. **注册**：`Tool.define(id, init)` 定义 → `registry.ts` 收集 `builtin` → `tools()` 按 provider/model/agent/permission 过滤。`llm/request.ts resolveTools` 再用 `Permission.disabled` 过滤 + 按名排序（`request.ts:208-214`）。

**对齐方案（Evoloop）**：
1. **`EvoLoopTool` 补 `formatValidationError` 语义**：工具执行失败（参数错）→ 返回结构化 error 而非静默吞掉（`tools/executor.py` 改造：失败分类为「参数错误→回喂模型」/「环境错误→真实异常」）。
2. **统一截断下沉到 executor**：`AgentToolExecutor.execute_tool` 收尾统一过 `ToolOutputMemory`/截断器，工具作者不感知（对齐 `tool.ts:135`）。
3. **`ctx.messages` 透传**：给 `AgentToolExecutor` 传入当前消息流（现状 `execute_batch` 只拿 tool_calls），工具可读历史。
4. **hook 事件**：`tool.execute.before/after` 对齐（现状 `hooks.py` 的 `PRE_TOOL_USE`/`POST_TOOL_USE` 已类似，保持并统一命名）。
5. **工具描述瘦身**：参考 `task.txt`/`skill.txt` 的 Usage notes 风格（"何时用 / 何时不用"）。
6. **attachments 语义**（N7）：对齐 OpenCode `ExecuteResult.attachments`--工具结果可携带文件附件（截图/图片/PDF）直接进消息流供模型多模态消费与前端渲染。`EvoLoopTool` 的 `ToolResult` 增加可选 `attachments` 字段（mime+url/filename），executor 统一注入消息；`mobile_control`/`browser_control`/`desktop_control` 的截图、`read` 的图片、MCP image content 全走此通道（替代现状"存 artifacts 目录靠路径约定"）。

#### 10.2.1 工具面大幅简化（量化 + 收敛方案）

**现状（量化）**：
- 实际注册：**102 个** `@evoloop_tool`，分布在 25+ 个包（domain/tools、file、learning、atlas、mcp、macro、environment、terminal…）。
- 主 Agent 暴露面：`agent_main.yaml` 中 **supervisor 16 / worker 43 / finish 9**（去重 55 个）。
- OpenCode 对比：**固定 ~13 个内置工具**。

**为什么 43 个工具面是灾难**：
1. **选择熵（selection entropy）爆炸**：每次决策面对 43 个工具名+描述，光"决定用哪个"就消耗注意力与 token。
2. **功能重叠误选**：`browser_control`/`desktop_control`/`mobile_control`/`execute_command` 四套能干活；`run_macro`/`get_skill`/`list_skills`/`search_web` 多个"获取能力"入口。模型常选错/重复尝试——这是 Evoloop 需要 `_is_unverifiable_report`、`list_macros` 防猜名、discovery 反循环补丁的根本原因（工具太多模型记不住）。
3. **提示词污染**：工具 schema 本身进 system prompt，102 个全暴露会吃掉大量 token 且稀释高价值描述。
4. **维护成本**：25+ 包散落注册 + yaml 手写白名单，新增工具要记得加 yaml（今天 `search_native_tools`/`sql_query`/`write_wiki_page` 等全被注释掉就是维护崩溃证据）。

**收敛目标**：**三层出池模型**--102 个保留注册（供 `search_native_tools` 与能力检索）、**~30 进可用池**（配置可选）、**15 个进默认面**（核心 12 + `run_macro` + `macro` + `remember`）；具身任务（browser/desktop/mobile 检测到目标）按需追加至 ≤18。低频/垂直能力（Atlas/Wiki/Codebase/宏管理/MCP）全部走「索引 + 按需加载」，不占默认工具面。

**收敛对照表（worker 43 → ~15）**：

| 现状（worker 池） | 简化后 | 理由 |
|---|---|---|
| mobile_control / browser_control / desktop_control / execute_command | `execute_command` + `browser_control` + 按需 MCP | 具身执行合并，去重叠 |
| run_macro / list_macros / read_macro / create_macro / update_macro / delete_macro | `run_macro` + `macro(name)`（管理走后台通道） | 对齐 Skill「索引+按需」，不占 Agent 工具面 |
| get_skill / list_skills / delete_skill / update_skill / reconcile | `skill(name)`（§5） | 同 Skill 按需 |
| remember / recall / search_history / forget_tool_outputs / recall_tool_output / list_forgotten_outputs / save_concepts / query_concepts | `remember` / `recall` / `search_history` | 记忆工具瘦身（forget 移入代码层自动管理） |
| create_plan / update_step_status / create_todo / list_todos / complete_todo / cancel_todo / create_project_tasks | `plan` / `todo` facade | 同类能力合并 |
| list_agents / send_agent_task / complete_task / route_to / cancel_subagent / cancel_all_subagents | `task` 工具（§4） | 子代理/A2A 统一入口 |
| search_web / wait_for / inspect_task_health / list_vault_credentials / request_secure_credential | 高频保留，低频走 MCP/按需 | 按使用频率保留 |

**落地要点**：
- `agent_main.yaml` 收敛主 Agent 工具池到默认 15 个；其余工具保留注册但不进默认池（`get_all_capabilities` 仅用于 `search_native_tools` 检索，`manager.py:165-177` 已有此语义）。
- **`search_native_tools` 去留**：默认面收敛到 15 后，模型不再需要大目录检索工具，`search_native_tools` 从 Agent 工具面移除；其检索函数保留在服务层（供 Atlas/工具管理 UI 使用），不再作为 `@evoloop_tool` 暴露。
- MCP 渐进披露（`tools/manager.py:104-155`）保留但**换宿主**：显式请求源从 `ExecutionTicket.mcp_servers_required` 改为 **`task` 工具参数**（子代理场景）与 **`use_mcp_server` 工具**（主 Agent 场景，写回 `EvoContext`）；无显式请求时默认只注入已连接全局 MCP。
- 工具描述瘦身：每条描述聚焦"何时用/何时不用"（Usage notes 风格）。
- **单发/会话两路径合并**（N8）：`background_agent/runner.py` 的单发 `run_agent_background` 与会话 `run_agent_session` 在阶段 B 统一为**同一条 `run_agent_loop`**（差异仅在 delivery 包装与 gate 等待），消除双执行体维护成本；`runner.py` 保留为薄适配壳（构造 state/config/callbacks）。

#### 10.2.2 工具命名对齐 OpenCode

**OpenCode 工具名风格**：单词、动词/名词直给、职责互斥、成对对称（`read`/`write`、`glob`/`grep`）。最终注册面（`registry.ts`）：`bash` `read` `glob` `grep` `edit` `write` `task` `webfetch` `websearch` `todo` `skill` `question`（+实验 `patch`/`lsp`/`plan`）。

**Evoloop 现状命名问题**：`execute_command`/`read_file`/`find_files`/`grep_search` 冗余后缀；`ask_human`+`ask_confirm` 双入口；todo 四件套（`create/list/complete/cancel`）；委派五件套（`route_to`/`list_agents`/`send_agent_task`/`complete_task`/`cancel_subagent*`）。

**命名映射表（现名 -> OpenCode 对齐名）**：

| 类别 | Evoloop 现名 | 对齐名 | 说明 |
|---|---|---|---|
| 文件 | `execute_command` | **`bash`** | 对齐 OpenCode bash（PTY/沙箱语义不变） |
| 文件 | `read_file` + `list_dir` | **`read`** | read 支持文件+目录（OpenCode 同语义） |
| 文件 | `find_files` | **`glob`** | |
| 文件 | `grep_search` | **`grep`** | |
| 文件 | `edit_file` | **`edit`** | |
| 文件 | `write_file` | **`write`** | |
| 文件 | `delete_file` / `move_file` | `bash` 覆盖 | 低频，不再单列工具 |
| 检索 | `search_web` | **`websearch`** | |
| 检索 | （无） | **`webfetch`** | 新增（OpenCode 同名同义） |
| 交互 | `ask_human` + `ask_confirm` | **`question`** | 合并为单入口（OpenCode question 语义） |
| 计划 | `create_todo`/`list_todos`/`complete_todo`/`cancel_todo` | **`todo`** | 合并 facade（OpenCode todowrite 语义） |
| 计划 | `create_plan`/`update_step_status`/`create_project_tasks` | **`plan`** | 合并 facade |
| 委派 | `route_to`/`list_agents`/`send_agent_task`/`complete_task`/`cancel_subagent`/`cancel_all_subagents` | **`task`** | 统一子代理/A2A 入口（§4） |
| 技能 | `get_skill` | **`skill`** | 索引+按需加载（§5） |
| 技能 | `list_skills` | 删除 | 索引已在 system prompt |
| 宏 | `list_macros`/`read_macro` | **`macro`** | 合并为按需加载（§5.7） |
| 宏 | `run_macro` | **`run_macro`**（保留） | 确定性执行，一等公民 |
| 宏 | `create_macro`/`update_macro`/`delete_macro` | 删除（管理通道） | 不占 Agent 工具面 |
| 记忆 | `remember`/`recall`/`search_history` | 保留原名 | Evoloop 特有资产 |
| 记忆 | `forget_tool_outputs`/`recall_tool_output`/`list_forgotten_outputs` | 删除 | 代码层自动管理（§6） |
| 记忆 | `save_concepts`/`query_concepts` | `query_concepts` 保留、`save_concepts` 并入 `remember` | 瘦身 |
| 图引擎 | `update_blackboard`/`report_outcome`/`inspect_task_health` | 删除 | 随图引擎移除 |
| 具身 | `browser_control` | **`browser`** | 去冗余后缀 |
| 具身 | `desktop_control` | **`desktop`** | |
| 具身 | `mobile_control` | **`mobile`** | |
| 具身 | `clipboard`/`open_app`/`list_devices`/`analyze_image`/`verify_ui_state`/`wait_for` | 保留原名 | 具身特有，OpenCode 无对应 |
| 凭证 | `list_vault_credentials`/`request_secure_credential` | 保留原名 | 安全通道 |

**目标工具面（主 Agent，默认 15 / 具身追加至 ≤18）**：

```
核心 12（OpenCode 同名）：bash  read  glob  grep  edit  write  task  webfetch  websearch  todo  skill  question
特有 3（默认）：          run_macro  macro  remember
按需 3~6（具身任务注入）：browser  desktop  mobile（recall/search_history/vault 等低频按需）
```

**迁移策略**：
1. 工具改名走 `@evoloop_tool(name=...)` 别名注册，旧名保留兼容期（内部映射），`agent_main.yaml` 直接用新名。
2. 提示词（`.txt`）与 doom_loop 检测、审计 `tool_stats` 一并切换到新名。
3. 存量 DB 消息中的旧工具名不迁移（历史只读）；新会话全部新名。

#### 10.2.3 工具功能对齐矩阵（同名 ≠ 同功能）

> 命名对齐只是第一步。逐工具对比 OpenCode 与 Evoloop 的**实现语义**后，结论是：**部分对齐、部分有差距、部分 Evoloop 反超**。对齐原则：语义向 OpenCode 看齐，Evoloop 独有优势保留。

| 工具（对齐名） | OpenCode 实现 | Evoloop 现状 | 对齐动作 |
|---|---|---|---|
| **`read`** | 文件+目录一体（目录列 entries + symlink 解析，`read.ts:101-115`）；行级截断（2000 字符/行）；二进制采样检测（50KB sniff）；图片/PDF 转 attachments；未找到时**相似度匹配**建议 top3（`read.ts:76-99`）；LSP 预热（`lsp.touchFile`）；接近 token 上限警告；metadata.loaded 供 compaction | 仅文件（目录拒绝并提示用 `list_dir`）；未找到只列兄弟文件前 20（非相似度）；有**特殊格式提取**（pdf/docx/xlsx/mp3/mp4/html 走 content_extractor）与**大文件结构 outline** 预览（独有优势）；有行数+hash header | **合并**：`read` 支持目录（吸收 `list_dir`）；补行截断、二进制检测、图片转 attachment、相似文件建议、token 警告；保留 content_extractor 与 outline |
| **`edit`** | `oldString`/`newString` 精确匹配；`replaceAll`；多匹配报错；readonly 检测；错误信息教模型如何修复 | **更强**：`FileEditorService` 级联模糊匹配（cascading fuzzy）、`expected_hash` 乐观锁、multi_edit 原子批量、`verify_types` 类型诊断（exploration engine）、edit_preview | **保留 Evoloop 实现**，只对齐参数命名（`target/replacement` -> `oldString/newString` 语义）与错误回喂文案风格 |
| **`grep`** | ripgrep；include 过滤；`file:line:content` 输出 | ripgrep；`scope` glob；`case_insensitive`；MAX_MATCHES 截断 + refine 提示；输出格式一致 | **已对齐**，参数名 `scope` -> `include` 对齐，保留 case_insensitive |
| **`glob`** | pattern/path/limit | `find_files` 类似（pattern/path） | 已对齐，仅改名 |
| **`write`** | 路径+content；readonly 检测 | `write_file` 对等 | 已对齐，仅改名 |
| **`bash`** | `description` 必填（模型解释命令目的）；timeout；workdir；持久 session（shell id）；后台任务（bg） | **更强**：PTY 持久终端 + SIG marker 退出码捕获；Docker/Local **沙箱**；`affected_path` 解析供 diff 追踪；后台执行；HITL 审批 | **保留 Evoloop 实现**（沙箱/diff 是优势）；补 `description` 参数约定与 `timeout` 参数 |
| **`task`** | 子代理统一入口（subagent_type/description/prompt/task_id 续聊） | 无（`route_to` 是图信号非工具） | **新增**（§4），对齐 OpenCode 全语义含 task_id 续聊 |
| **`webfetch`** | url/format(text/markdown/html)/timeout | **缺失**（只有 `search_web`） | **新增**（OpenCode 同义：抓 URL 转 markdown） |
| **`websearch`** | query 走 provider（opencode/exa） | `search_web` 走搜索服务 | 已对齐，仅改名 |
| **`question`** | 单工具多问题（questions[] + options + multiple + header） | `ask_human` + `ask_confirm` 两入口 | **合并**为 `question`（多问题数组语义对齐） |
| **`todo`** | **单工具全量重写** todo 列表（一次调用传完整列表，避免多次调用） | 四件套（create/list/complete/cancel 分四次调用） | **合并为全量重写语义**（对齐 todowrite：一次传整个列表） |
| **`skill`** | `skill(name)`：require -> 权限 -> 返回 SKILL.md 正文 + 资源文件列表（`<skill_files>`） | `get_skill` 语义不同（猜名查询）；无索引+加载两段式 | **重写**（§5，对齐 OpenCode 全语义） |
| **`plan`** | OpenCode plan 是模式开关（plan/exit 工具） | `create_plan`/`update_step_status` 持久化计划（DB Plan/PlanStep + 前端面板） | **保留 Evoloop 语义**（结构化计划是资产），合并 facade 为 `plan` |

**结论与优先级**：
1. **已对齐/仅改名**（低风险）：`glob`、`write`、`websearch`、`grep`（微调）。
2. **Evoloop 反超、保留实现**（只调参数命名）：`edit`（模糊匹配+hash 锁+类型诊断）、`bash`（PTY+沙箱+diff 追踪）。
3. **需补齐功能**（中工作量）：`read`（目录支持/行截断/二进制检测/图片 attachment/相似建议）、`question` 合并、`todo` 全量重写语义。
4. **需新增**（阶段 A 核心）：`task`、`webfetch`、`skill`、`macro`。
5. **横切能力**（所有工具受益，优先级最高）：Schema 校验 + 错误回喂（`InvalidArgumentsError` 语义）、统一截断、`ctx.messages` 注入（§10.2 对齐方案 1-3）。

---

### 10.3 MCP 集成（OpenCode `mcp/index.ts` + `mcp/catalog.ts` + `session/tools.ts`）

**OpenCode 的 MCP 是"一等公民"**，工具/提示词/资源三通道全接入：

1. **生命周期**（`mcp/index.ts`）：
   - `local`（stdio 子进程）/ `remote`（StreamableHTTP 或 SSE，含 OAuth 自动发现，`index.ts:236-370`）两种类型。
   - 状态机：`connected / disabled / failed / needs_auth / needs_client_registration`（`index.ts:83-106`）。
   - 启动时并发连接所有配置的 server；`tools` / `instructions` / `prompts` / `resources` 缓存于 state。
   - `ToolListChangedNotification` 监听，服务器工具变化时刷新 defs（`index.ts:462-471`）。

2. **工具注入**（`session/tools.ts:390-490`）：
   - `mcp.tools()` 返回 `{ 命名key: McpTool }`，命名 = `sanitize(server)_sanitize(tool)`（`catalog.ts:119`）。
   - 每个 MCP 工具包一层：参数 schema 转 AI SDK、执行时 `ctx.ask({permission: key})` 权限询问、结果 content 归一化（text/image/resource 分类处理，`tools.ts:426-462`）、统一 `truncate.output`。
   - **MCP 工具与内置工具同一张 tools 表**，无特殊路径。
   - `mcp.instructions()`（`index.ts:615-625`）→ 注入 system `<mcp_instructions>`，仅当有 connected 且工具未被权限禁用。

3. **资源通道**（`session/tools.ts:136-386`）：
   - 若有 server 声明 `resources` 能力，动态加 `list_mcp_resources` / `list_mcp_resource_templates` / `read_mcp_resource` 三个内置工具。
   - 二进制资源（PDF/图）转 attachment；超限（10MB）或非支持 MIME 则省略并说明（`tools.ts:439-459`）。

4. **OAuth**（`mcp/auth.ts` + `oauth-provider.ts`）：远程 server 自动发现 OAuth，启动回调 server，浏览器打开授权 URL，状态防 CSRF（`index.ts:806-942`）。

**对齐方案（Evoloop）**：
1. **工具命名统一**：Evoloop 现有 `parse_mcp_tool_name`（`tools/manager.py`）+ `McpCatalog.toolName` 对齐为 `sanitize(server)_sanitize(tool)`，避免 server/tool 名含非法字符导致 LLM 调用错。
2. **MCP 工具与内置工具同一执行路径**：现状 `manager.py` 已把 MCP 工具并入 `combined_map`（`tools/manager.py:104-155`），保留；但包一层统一「权限 ask + content 归一化 + 截断」（对齐 `session/tools.ts`）。
3. **`<mcp_instructions>` 注入**：现状 `system.ts mcp()` 已有（`system.ts:119-135`），保留；收敛到「有 connected 且工具未禁」才注入。
4. **资源工具**：新增 `list_mcp_resources` / `read_mcp_resource` 三个内置工具（对齐 OpenCode），现 Evoloop 已有 `mcp/tools/`（list_resources/read_resource），补动态注入逻辑即可。
5. **远程 OAuth**：Evoloop `mcp/auth` 已有 OAuth，保留；补 `needs_auth` 状态与浏览器打开授权流程（对齐 `index.ts`）。
6. **统一超时**：`requestTimeout` 语义（server 级 timeout 配置 + 全局兜底）对齐。

---

### 10.4 四等公民统一模型：Tool / Skill / MCP / Macro

> ⚠ **Evoloop 比 OpenCode 多一个一等公民：Macro**。OpenCode 只有 Tool / Skill / MCP 三类一等公民；Evoloop 重构后是**四类**——Tool / Skill / MCP / **Macro**。设计时必须四者并列，不可把 Macro 归入 Tool 或 Skill 之一。

#### 10.4.1 四等公民对比

| 维度 | Tool | Skill | MCP | Macro（Evoloop 独有） |
|---|---|---|---|---|
| 本质 | 确定性能力函数 | 指令/SOP（提示层） | 外部服务工具集 | 可回放确定性脚本（执行层） |
| 定义位置 | `@evoloop_tool` | `SKILL.md` / `LearnedSkill` | MCP server 配置 | `learning/macro/`（Trace 编译） |
| system 索引 | 工具 schema（description） | `<available_skills>` | `<available_mcp>` + `<mcp_instructions>` | `<available_macros>` |
| 按需加载 | 直接调用 | `skill(name)` | 渐进披露 `use_mcp_server` | `macro(name)` / `read_macro` |
| 执行 | `AgentToolExecutor` | 模型读正文自行动 | MCP `callTool` | `run_macro` 确定性回放 |
| 生命周期 | registry 注册 | pending_review→verified | connect/disconnect/状态机 | 自动创建→校验→激活 |
| 权限 | `ctx.ask(permission)` | `skill` 规则 | `mcp:<server>:*` | HITL / `required_benefit` |

#### 10.4.2 统一注入与治理

1. **统一索引区**：`main.txt` 动态块按需追加四段：
   ```
   <available_skills> … </available_skills>
   <available_macros> … </available_macros>
   <available_mcp> … </available_mcp>
   <mcp_instructions> … </mcp_instructions>
   ```
   各段只放 name+description（截断），正文一律按需加载。
2. **统一工具表**：Tool / MCP 工具 / `skill` / `macro` / `run_macro` 全部进同一张 `AgentToolExecutor` 工具表，无特殊路径（对齐 OpenCode `session/tools.ts`）。
3. **统一权限**：四者都走 `ctx.ask` / `Permission` 规则（`skill`、`mcp:<server>:*`、`run_macro` 各自的 permission 名）。
4. **统一截断**：四者输出都过 `truncate.output`。
5. **统一 hook**：`tool.execute.before/after` 对四者生效。

#### 10.4.3 迁移检查项

- [ ] `main.txt` 动态块含四段索引（skills / macros / mcp / mcp_instructions）
- [ ] 新增 `macro(name)` 工具（对齐 `skill(name)`，返回 MacroScript 概览）
- [ ] `run_macro` 保留确定性执行 + WEB_POLICY 自愈回退，不因重构删除
- [ ] Macro 自动创建（`MacroCreatorService`）改为代码层触发，不从 prompt 规则
- [ ] `macro_usage.j2` 反循环规则随重构移除（防循环入代码层）

---

## 11. 预期收益（含提示词/工具/MCP/Macro）

| 维度 | 重构前 | 重构后 |
|---|---|---|
| 简单任务 LLM 调用 | 3+ 跳（Supervisor/Worker/Finish） | **1 跳** |
| 长程能力 | 每跳失忆（消息过滤 + 票摘要） | 连续消息流，完整回看 |
| 上下文管理 | 节点 filter 破坏 + LLM 主动 forget | 系统侧自动截断 + 窗口，不破坏 |
| 防循环 | 靠 prompt 协议（unverifiable / verification_blocked_topics） | 代码层 doom_loop 检测 |
| 人格 | 三套人格切换税 | 单 Agent 一致 |
| 子代理 | 图节点 + 聚合 LLM 轮 | task 工具 + 父 Agent 自聚合 |
| 技能 | 全量 SOP 注入 + 猜名 get_skill | 索引注入 + `skill` 工具按需加载 |
| 提示词 | 三套人设 + 海量 fragment 全量注入 | 静态分层 + 动态按需，`<system-reminder>` 小块 |
| 工具 | 静默吞错 + 全量池（102 注册 / worker 43） | Schema 校验回喂 + 统一截断 + **主 Agent 默认 15 工具**（102 注册 / 30 可用池）+ `ctx.messages` + attachments |
| MCP | 特殊路径 + 命名不统一 | 一等公民：同一 tools 表 + 命名统一 + 资源通道 + OAuth 状态机 |
| **Macro** | 混在工具池 + prompt 反循环规则 | **一等公民**：`<available_macros>` 索引 + `macro(name)` 加载 + `run_macro` 执行，与 Tool/Skill/MCP 平级 |
