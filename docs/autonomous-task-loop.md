# 自主任务循环（Autonomous Task Loop）设计方案

> 状态：**已实现**（阶段〇-八全部落地；阶段八=2026-09-23 全局设计收敛，新契约以 §阶段八 为准）
> 范围：evoloop 引擎侧任务/调度/执行机制 + 界面设计（通用能力，不绑定任何业务项目；商城 mall 仅作为首个接入项目贯穿举例）
> 关联文档：`docs/capability-packages-refactor.md`（能力包）、mall 侧 `mcp-server/AGENTS.md`（原子能力矩阵，项目侧示例）；`docs/task-system-fullflow.md` 已并入本文档（§9 界面 / §13 断层），仅存指针

---

## 1. 背景与问题

### 1.1 业务目标

让 Agent 尝试接管一个业务系统的运转，用户不逐条下达指令，只做**规划任务、验收结果、处理异常**。首个落地项目即「尝试接管一座商城」：从开店开始的选品 → 开店 → 上架 → 冷启动 → 日常运营。

心智模型（贯穿全文）：

```
evoloop 项目（Agent 工作区：project.json / 能力包 / 值守配置）—— 操作方/接管者
      │  经 MCP 原子能力矩阵访问
      ▼
商城（被接管的外部业务系统）
```

- 项目 ≠ 商城：项目承载"接管"这件事，商城是被接管对象，两者以 MCP 工具面为界——换一个接管对象（CRM、供应链、内容站）只换能力包与任务数据，调度与执行层零改动。
- 「尝试」= 渐进接管：自主度由验收门控调节（T3/T4 先放权、T1/T2 人在环、rejected 回炉），接管强度随信任积累逐步上调，不是一键全自动。

### 1.2 现状机制盘点（设计期快照；落地结果见 §11 阶段记录）

| 资产 | 设计期状态 → 落地结果 |
|---|---|
| business_poll_prompts（mall project.json 话术） | 6 条 prompt+固定间隔 → **已退役**：checklist 数据化迁入 recurring 任务（阶段三） |
| AutonomousTask | 系统级触发器 → **收缩为纯定时器**，只剩渠道轮巡职责 |
| Todo | 已退役（plan 接管执行追踪） |
| Plan / PlanStep | run 内计划 → 已挂 task_id（4.2） |
| schedule 工具 | 只能调宏 → 沿用（宏定时域） |
| 值守调度护栏 | 完整保留（见 5.5） |
| 收尾管线 | SESSION_COMPLETED 不回写队列 → 保留现状（提案走 Agent 工具，见 6.4） |
| mall MCP 原子矩阵 | 105 原子工具 + 四件套风险标注 → 原样继承 |

### 1.3 结构性问题

1. **话术 ≠ 任务**：business_poll_prompts 每条是「写死的 prompt + 独立间隔」。prompt 在配置时固化，而"该干什么"取决于运行时业务状态；任务无状态机、无验收、无依赖、无归属，Agent 不可读写。
2. **自排程闭环缺失**：Agent 运行中发现的待办（缺货、差评、异常订单）没有回流通道——todo 只记录不触发；schedule 只能调宏；tick 平铺扫 next_run_at 无优先级；completion 管线不回写队列。「run 内事件 → 任务队列 → 再派发」这条弧是断的。
3. **决策点错位**：加一个巡检域 = 改配置发版；调度粒度绑死在话术上，而非绑在任务的 due_time / priority 上。
4. **发现与执行耦合**：每条巡检 prompt 既发现异常又直接处理，一次 run 干两件事，上下文长且审计混杂。

---

## 2. 设计原则

0. **系统只排队，拆分归 Agent（最高准则）**。对系统而言任务就是任务：只要有未处理任务，按序出队交给 Agent；先后 = 排序字段（priority / due_at / 树序），系统不做任何二次分类。计划、步骤、子任务、当场干还是建新任务——全部是 Agent 的运行时行为（plan 工具 / 建任务），系统不预设、不参与。
1. **调度唤醒，任务做数据**。定时器只负责把 Agent 叫醒；调度器不知道业务，业务在任务行和 SOP 包里；prompt 不承载计划，计划是 Agent 现场做的。
2. **任务状态在 DB，thread 只是工作台**。thread 可轮转、可截断、可换新，状态不丢。
3. **门控统一，不设任务类型**。任何 run（wakeup / 消息会话 / 周期任务）中的写动作都过同一套 T1-T4 风险门控——"当场干还是建提案"是运行时决策，不固化为 schema 类型；系统侧唯一的"分"是调度优化用的车道（category），且它是可缺省的资源隔离键（缺省进 default 车道串行），不是任务分类。
4. **一条执行链**。三个入口（用户定义任务 / 用户临时消息 / 第三方系统事件）+ 一个派生（Agent 提案）汇入同一张任务表、同一条执行路径；入口只影响任务的来历，不影响执行方式。
5. **验收按风险分级**。复用 mall MCP 四件套的 `[risk:T1-T4]` 语义：T1/T2（资金）必须验收后完结，T3/T4 自动通过、事后抽查。
6. **护栏全部继承**。认领即推进、串行派发、在飞登记、doom-loop、G4 确认门控、HITL 挂起恢复——与本方案正交，原样保留。

---

## 3. 总体架构

> **已实现修订（2026-09-21，以代码为准）**：设计稿的"心跳 tick 扫 project_tasks + 车道并行"已被**单 drainer 常驻循环**取代——tick 不再派发 project_tasks（`AutonomousTask` 收缩为纯定时器，只剩渠道轮巡职责），派发只发生在 supervisor。设计期"车道并行"未实现：当前为**全局串行 drain**，category 仅用于派发排序与域装配，不是并行车道。见 5.1/5.2 已实现修订。

```
一张任务表 · 三入口一派生                 常驻 supervisor（API 进程，APP_STARTED 启动）
┌────────────────────────────┐        事件驱动（run 终态/队列变更唤醒）+ 60s 兜底
│ 入口① 用户定义任务（含日常性） │        ┌────────────────────────────────────┐
│ 入口② 用户临时消息（转化协议） │  ──▶   │ run_supervisor_forever 循环：        │
│ 入口③ 第三方系统事件           │        │  reconcile(判死/回队/孤儿HITL豁免)    │
│ 派生  Agent 提案（proposed）   │        │  → auto_retry_failed_tasks           │
└────────────────────────────┘        │  → dispatch_due_tasks（串行 drain）   │
                                      │  → wait(wakeup, 60s) → 每300s强制reconcile │
                                      └────────────────────────────────────┘
                                                │
                     每任务一个 wakeup run（唤醒 prompt + tasks 行为协议）
                     ├─ 派发即认领（in_progress + last_thread_id + dispatch_count++）
                     ├─ 域装配（capability profile 按域预选包/工具面）
                     ├─ 执行（MCP 原子工具）→ 计划推进 → 状态实时落库
                     ├─ 结构化自检 → T3/T4 自动完成 / T1-T2 waiting_acceptance
                     └─ 新发现 → create Task(source=agent, proposed)
```

### 3.1 任务状态机

> **已实现修订（2026-09-21，`constants.py QUEUE_TRANSITIONS` 为准）**：设计稿的 `planned`/`accepted` 态未采用——实际状态集为 `proposed / pending / in_progress / self_checked(瞬态) / waiting_acceptance / completed / failed / cancelled`。T3/T4 自检通过**自动 completed**（by=system:auto 可审计），T1/T2 经 waiting_acceptance 由用户验收后 completed；rejected 不是状态而是验收裁决（feedback 回流 → 任务回 pending 重跑）。

```
proposed ──用户确认──▶ pending ──认领/agent take──▶ in_progress
   ▲                                              │
   │                     self_check（瞬态，不落库）  │
   │                        ├─ T3/T4 无 origin/无需signoff → completed (system:auto)
   │                        ├─ T3/T4 有 origin → waiting_acceptance → 监察评审
   │                        ├─ T1/T2 或 requires_human_signoff → waiting_acceptance → 人验收
   │                        └─ recurring → 回 pending（next_run_at 推进，等下个周期）
   └── rejected（acceptance feedback → 回 pending 重跑）◀── 用户验收不通过
failed ⇄ pending（人工重跑回队，requeue≤3 防毒）；failed 有 auto-retry 预算（1 次/10min 退避）
```

- `proposed`：Agent 派生提案 / 外部低可信事件，需用户确认才入列。
- `in_progress` 由**派发即认领**写入（系统侧认领原语，见 3.2），agent 的 `tasks take` 对同线程幂等确认。
- 验收不通过必带反馈文本（`acceptance.feedback`），回流后下一轮计划必须响应。

### 3.2 核心循环时序

> **已实现修订（2026-09-21）**：设计稿的 tick 扫描已由 supervisor 循环取代。扫描条件以 `TaskQueueService.claim_due_tasks` 为准——注意 **recurring 只认 next_run_at 门控**（2026-09-21 修复：原 `due_at IS NULL` 分支对 recurring 恒命中，明日任务被判到期而爆发连跑）；**项目分闸**（customer_service_duty.enabled）是派发前的 opt-in 闸，闸关时到期任务"挂起"并打日志，开闸即恢复——这是任务的"不激活"开关（pid=0 工作空间任务豁免）。

```
supervisor 循环（事件驱动 + 60s 兜底，API 进程内，纯代码扫描，无 LLM）
  ├─ reconcile_stranded：启动判死遗留 running/stopping；稳态判死悬挂 run；
  │   终态线程上的悬置任务回队（requeue≤3 防毒）；孤儿 human_interrupt 回队
  ├─ auto_retry_failed_tasks：failed 且预算内（1 次）→ 回队（10min 退避）
  ├─ dispatch_due_tasks（串行 drain，三道闸）：
  │   ① 全局总闸（customer_service_duty.enabled，托盘语义=什么都不跑）
  │   ② 配额熔断（duty_paused）
  │   ③ claim_due_tasks：status=pending ∧（one-shot: due_at 空或≤now ∨
  │      recurring: next_run_at≤now）∧ dependencies 全 completed ∧ 项目分闸开
  ├─ 认领：recurring 认领即推进 next_run_at 落盘；one-shot 派发即认领
  │   （in_progress + last_thread_id + dispatch_count++；派发失败回滚 pending）
  ├─ 按序派发 wakeup run（每次认领一个，await 收尾再下一个）
  └─ 无到期任务 → wait(wakeup 事件, 60s)（事件只做加速，不丢存活）
```

---

## 4. 数据模型

> **修订说明（2026-09 二次评审）**：初稿曾设计独立 `ops_tasks` 新表——经核实为**重复建设**。系统已有 `ProjectTask`（`app/models/project.py`）：层级任务树、task_data 内含 priority/category/acceptance_criteria、execute_task 已打通「任务 → dispatch_agent_run → 后台执行」链路（`api/routes/tasks.py:136`）、get_next_executable_task 已有队列语义（`api/routes/subtasks.py:123`）、EvoCloud 双向同步（`core/evocloud/bridge/sync_tasks.py`）。本方案改为**扩展 ProjectTask**，不建新表。任务就任务，无 "Ops" 前缀——evoloop 是通用 Agent 系统，商城只是它覆盖的一个项目。

### 4.1 Task = ProjectTask 扩展（任务队列 SSOT）

**已有、不动**：id / project_id / member_id / parent_id（任务树）/ status / progress / task_data（title, description, priority, category, tags, acceptance_criteria）/ EvoCloud 同步三字段 / created_at / updated_at。

**增量字段**（alembic 迁移）：

```
project_tasks +
  description         text             任务正文（Agent 的完整可执行指令，一等列：
                                         前端可编辑、Agent 工具可读写；task_data 不再重复）
  type                varchar(20)      once / recurring（与 trigger_spec 一致性由
                                         create_task 强制：trigger 非空即 recurring）
  source              varchar(20) idx   创建者：user / external / agent（缺省 user，存量数据归 user）
  provenance          json null         派生路径：{kind: message|patrol_run|agent_run, ref: thread/任务/run id}
  source_ref          json null         来源回执：{event_id, order_no, ticket_id…}
  dedup_key           varchar unique null  幂等键：{source}:{event_id}，兜 webhook 重试
  risk_level          varchar(4) null   验收分级 T1-T4（继承 mall MCP 四件套语义，通用化：资金/不可逆/可逆/低危）
  due_at              timestamptz idx   到期/希望开始时间（调度扫描键）
  trigger_spec        varchar(255) null 非空 = 周期任务（cron 或 interval:秒），由 tick 认领时推进
  next_run_at         timestamptz idx   周期型下次执行时间
  self_check          json null         结构化自检报告：{verdict, checks:[{name,pass,evidence}], deviations}
  acceptance          json null         验收回执：{by, at, verdict, feedback}
  last_thread_id      varchar null      最近一次执行的工作台 thread（看板钻取用）
```

- `task_data.category` 从开发向枚举（frontend|backend|database）放开为**通用域枚举**，由各项目按域声明（capability profile 对齐），商城项目取值如 orders/refunds/stock/goods/promotion/finance/store_init——**category 是车道键 + 装配键，不是商城专属概念**。
- 依赖表达：**`task_data.dependencies` 列表**（**已实现修订 2026-09-21**：设计稿"用任务树不另设 depends_on"未采纳——实际是显式依赖列表，`claim_due_tasks` 检查全 completed 才放行，派发时上游 `last_result` + artifacts 经 `_build_upstream_context` 注入执行 payload；任务树 parent_id 表达的是父子归属，两套语义并存）。
- **status 扩展**：现值 pending/in_progress/completed/failed 为 String(50) 自由值，直接扩展验收态：`proposed → pending → in_progress → self_checked → waiting_acceptance → completed(accepted) / failed(rejected)`，无迁移风险。

### 4.2 Plan 关联改造

`Plan` 增加 `task_id`（nullable FK → project_tasks）。一个任务可产生多个计划版本（rejected 回流 → 新计划），PlanStep 不变。execute_task 的 thread 关联模式（thread_id 带 task_id）沿用，`last_thread_id` 记录最近工作台供看板钻取。

### 4.3 各既有概念的角色界定

| 概念 | 界定后的职责 |
|---|---|
| **ProjectTask** | 任务队列 SSOT：三入口 + Agent 派生合一（用户 WBS / 消息转化 / 外部事件 / Agent 提案），调度与验收单位 |
| AutonomousTask | 系统级触发器：值守轮巡（wecom/kf）、宏定时、Android 自主任务。**不掺任务语义，不退役** |
| ~~Todo~~ | **已退役**（引擎侧 domain/models/templates/API 已清理，`plan` 已进默认工具面接管"会话执行追踪"） |
| Plan | run 内执行计划，挂上 task_id 后成为任务的"过程资产"。**唯一执行追踪资产**（读通道：active_plan_context 注入；写通道：默认面 plan 工具） |

> 2026-09 收尾核查：todo/plan 分裂脑已消除（读写通道同指 plan），但留有 4 个尾巴，见 10.1 收尾清单——其中 mall 域白名单修复是本方案阶段一的**硬前提**。

---

## 5. 调度与执行

### 5.1 触发与队列（已实现修订 2026-09-21）

> 设计稿的"心跳 tick 复用 main.py asyncio 循环"已被 **`domain/tasks/runtime/supervisor.py::run_supervisor_forever`**（main.py lifespan 拉起，APP_STARTED 事件）取代——**tick 已摘除 project_tasks 派发**，`SchedulerService.dispatch_task` 只剩值守轮巡触发器职责（非值守行到达即按"迁移残留"防御性跳过，`infrastructure/scheduler/service.py:130`）。防重护栏同样是进程内存态，**单调度实例硬约束**不变（WORKERS=1）。"事件直派"未实现插队通道——紧急任务随下一个 drain 周期出队（事件唤醒保证 ≤60s）。

- **队列分工（现状）**：值守渠道轮巡（wecom/kf 的 poll_once）由 AutonomousTask 定时器在 `dispatch_task` 内内联 await（机械采集不烧 LLM）；任务队列排空只发生在 supervisor。Huey/Celery 队列承载其他 worker 消费（重活）。
- **misfire/离线补跑**：supervisor 启动先 `reconcile_stranded(startup=True)` 判死遗留现场，队列状态在 DB——重启后任务按 pending/due 自然重派，无需 jobstore。

### 5.1.1 队列组件选型（2026-09 调研，结论存档）

> 完整逐组件评审表曾在此（APScheduler/Huey/Celery/persist-queue/Taskiq/Procrastinate/Temporal 类）；**结论：三层里触发层不需要组件**——扫描式架构（supervisor + `next_run_at`）天然内建离线补跑与 coalesce，APScheduler 卖点被免费满足，引入只会制造第二份调度真相（jobstore vs DB），违反"系统只排队"；消息层维持 **Huey（embedded）/ Celery（full）** 双轨随 `EMBEDDED_MODE` 切换；任务管理层自建（project_tasks DB-as-queue，本方案核心）。**全程未引入新依赖**。双模式均为双进程：API 进程（supervisor/值守）+ 队列 consumer/worker；单调度实例约束两模式均成立。


### 5.2 调度排序与线程模型（已实现修订 2026-09-21）

> 设计稿的"车道并行/同车道合派/thread 按天轮转"未实现。实际形态（`dispatcher.dispatch_due_tasks` + 实测日志验证）：

- **全局串行 drain**：同一时刻只跑一个 wakeup run（`_run_wakeup_with_deadline` await 收尾再认领下一个）——简化了车道锁，护栏等价（无并发即无竞态），代价是多任务吞吐串行化。
- **category 的实际角色**：派发排序键之一（priority → due → category，`_dispatch_order_key`）+ 域装配 hint（wakeup 派发注入 intent_hint，profile-first）。**不是并行车道，也没有车道锁**。
- **thread 命名（实测）**：纯工作项 `wakeup_{project_id}_{task_id}`（一次性，1:1 plan，每轮新 thread）；contact 任务 `wakeup_{project_id}_{contact}`（固定线程，客服多轮对话历史跨任务累积）；断链续跑不靠 thread 轮转，靠任务行状态 + 产出注入。

### 5.3 断点续跑与 HITL

- run 内**每完成一步即写回**任务行 status / PlanStep / self_check；max_steps 打断或进程重启后，下一个 wakeup 按 `in_progress` 续跑（进度读 DB，不依赖内存）。
- HITL 挂起（T1/T2 确认、doom-loop 询问）：任务行标记在飞 + 会话存活判定（复用 `_BUSINESS_PENDING` 语义），用户答复 → `HITLOrchestrator.resume_and_persist` 恢复原 run；车道锁等 delivery 完成才释放。

### 5.4 唤醒 prompt（已实现修订 2026-09-21，模板 `task_wakeup.prompt.j2`）

> 设计稿的"扫任务列表直到清空"未采用——实际是**每次认领恰好一个任务**派独立 run（串行 drain 的另一半）。实测 prompt 全文见运行日志，要点：
>
> **二次修订（2026-09-22 实测后瘦身）**：模板从 30 行缩至 4 行——Decision discipline / Protocol / Forbidden 迁入值守人格 `main.duty.txt`（「值守纪律」节）。动机：三处重复注入（模板/人格/tasks 工具 docstring）与"系统只排队，拆分归 Agent"原则冲突，且 T1/T2 门控的真执行者是引擎 G4 门控而非 prompt 自觉；实测瘦身对照 run（同量级只读任务）：llm_calls 14→5、input tokens 140K→39K。语言分层：模板纯英文、人格纯中文，禁止混排。
>
> **三次修订（2026-09-22，废除合成模板）**：`task_wakeup.prompt.j2` **删除**。最终形态——**任务描述（description）即第一条 human 消息的 content 全文**（不经任何模板包装；upstream_note 作为任务输入数据允许拼接）；任务元信息（id/status/priority/risk/due/category/feedback）改走**系统提示词层**：dispatcher 将 `duty_task` 块写入 metadata（dispatcher.py `dispatch_due_tasks`），`prompts.py` duty 分支渲染新模板 `core/agent/main.duty.task.txt` 注入（feedback 行 Python 侧条件组装，render_prompt 仅支持占位符替换）。测试契约同步更新：`test_dispatch_orchestration` 断言 message_content == description 原文、title/id 走 `metadata.duty_task`；`test_rejected_feedback_in_payload` 断言反馈不再进入 human 消息。行为注意：消息纯净后 Agent 首轮可能不调 tasks 工具（仅回答内容），由「run 结束任务未推进 → reconcile 回队重派」护栏兜底（2026-09-22 实测第二次 run 正确收口）——护栏不是缺陷，是消息纯净化的必要配套。
>
> **四次修订（2026-09-23 实测事故，pid=0 域解析 fail-open）**：`resolve_wakeup_domain` 对 **pid=0（工作空间任务）直接返回 None**（跳过 profile-first 与 L1）。事故链：Upwork 侦察轮描述被 L1 高置信分类为 `ecommerce`（conf=0.77 ≥ 0.6）→ `intent_hint.domain` 注入 run metadata → 引擎按域装配继承了商城项目 profile 的 `native_tools` 白名单（`[webfetch, websearch, plan, skill, question, tasks]`）——bash/文件工具全被裁掉 → Agent Reach 技能加载成功但 `opencli` 无处执行、`lead-radar/` 无法落盘、webfetch 被 Cloudflare 拦截 → Agent 按值守纪律 HITL 提问挂起（该半行为正确）。根因：工作空间任务不绑定任何项目域，L1 按措辞猜域会将任务随机装入某个项目的受限 profile。此前雷达轮能跑通纯属低置信（coding_dev conf=0.57）侥幸 fail-open。回归测试：`test_workspace_project_fails_open`（pid=0 高置信命中也不跑 L1）。

```
You are this project's duty Agent (autonomous duty). One due task (category `default`):
- [任务行] id / status / 标题 / priority / risk / due
  instruction: 任务描述（+ 上游产出注入）

Decision discipline（信任契约——连续值守的运行前提）:
- 指令/证据/风险全清晰 → 一撸到底；T1/T2 有疑虑、指令歧义、3 次真尝试仍阻塞
  → 必须用 `question` 提问等人（挂起便宜、值守不停摆），严禁静默乱猜。
- NEVER fabricate business data；诚实的"我阻塞了，需要你拍板"优于自信的编造。

Protocol:
1. `tasks` take（绑定任务，幂等）-> `plan` create -> 执行（MCP 工具，T1/T2 不过门控）->
   结构化自检 -> `tasks` update_status（completed 必填 result）
2. 新发现待办：`tasks` create(source=agent) → proposed，不自行扩范围
3. recurring 下一轮由系统推进；任务状态以 DB 为准，thread 只是工作台。
```

业务知识全部在能力包 SOP（mall-orders / mall-refunds / store-init…），prompt 只定义行为协议。

### 5.5 保留的护栏清单（已实现修订 2026-09-21——队列护栏已迁 domain/tasks/runtime/）

| 护栏 | 实际位置 |
|---|---|
| 派发即认领（claim-then-persist）+ FAILED 回滚 + take 幂等 | `domain/tasks/service.py`（claim_for_dispatch / release_dispatch_claim / take_task） |
| 派发熔断 dispatch_count ≥ 5 | `domain/tasks/constants.py DISPATCH_CLAIM_CIRCUIT_LIMIT` + `dispatcher.py` |
| recurring next_run_at 门控 | `domain/tasks/service.py claim_due_tasks`（2026-09-21 修复） |
| reconcile 判死（running/stopping）/悬置回队/孤儿中断/HITL 豁免 | `domain/tasks/runtime/reconciler.py` |
| 串行派发 / 单 run 30min 硬截止 / 单 drainer | `domain/tasks/runtime/dispatcher.py` + `supervisor.py` |
| 渠道轮巡护栏（在飞登记 300s/串行/硬超时） | `core/channel/duty/scheduler.py`（**仅渠道轮巡**） |
| doom-loop（3 次同签名 → HITL/确定性收尾） | `inference_engine` / `react/loop.py` |
| G4 确认门控（confirm_tools 未加载包不放行） | capability packages |
| HITL 挂起 / 恢复 / resume_runner | `core/hitl/` + `engine/resume_runner.py` |
| 上下文裁剪 / 超限折叠落盘 | `react/truncate.py` / ContextTrimmer |
| 错误单出口 ErrorEmitter | `engine/error_emitter.py` |
| 评审挂死 30min → 空结论收敛 | `runtime/reconciler.py`（review_timeout 兜底） |
| signoff/断链/24h 提醒推送 | 通知通道（duty 通知配置复用） |
| failed 断链：手机告警一次（防重标记），下游 blocked 等裁决 | 事件通知 |
| 配额熔断暂停派发（QUOTA_COOLDOWN） | `reconciler.py` QUOTA_EXHAUSTED → `pause_duty_for` |
| sqlite 连接池饱和 watchdog | API 基建层 |
| 依赖 MCP 陈旧连接（运维面） | 外部长驻服务需连接自愈或纳入巡检（2026-09-21 事故：mall PHP MCP 的 MySQL 连接陈旧不自愈 → 重启恢复，值守以提案上报） |

---

## 6. 任务入口：三入口 + 一派生

> 修订（2026-09 三评）：初稿将 patrol/agent 列为独立来源——分类错误。patrol 只是**用户定义的日常性任务**的一种执行类型（checklist 与 trigger 都由用户定义）；Agent 提案是**派生**，永远产生于前三入口触发的 run 过程中。入口与派生分记 `source` / `provenance` 两字段。

### 6.1 入口①：用户定义的任务（含日常性任务）

前端任务列表直接建（标题/描述/分类/优先级/截止/风险档按分类推断），入列即 pending（T1/T2 走验收，不需确认创建）。

**日常性任务 = recurring Task**（trigger_spec 非空），**无类型字段、不区分巡逻型/执行型**（2026-09 四评撤回初稿的类型拆分：那是把"当场干 vs 建提案"这一运行时风险决策错误固化成了静态 schema 字段；风险门控已由 T1-T4 统一覆盖，类型字段是重复表达）。到点触发 run，Agent 跑该域检查清单，其后所有动作走统一行为协议：

- 发现异常：T3/T4 且量小 → 当场处理（计划留步骤、自检覆盖）；T1/T2 → 建提案/HITL；量大 → 全部建任务排队（受 max_steps 约束）
- 例子：「每天 22 点生成经营日报」到点即做即验收（T4）；「库存巡检每 2 小时」发现售罄风险 → 下架类当场干、补货类（T1）建提案
- 巡逻日志（含"本次巡检无待办"）进看板；双轨期结束，`business_poll_check` 的 prompt 派发路径退役（护栏平移到新 tick）

### 6.2 入口②：用户临时消息（转化协议）

用户消息有三个到达通道：Web 对话（`/chat`）、值守渠道企微（wecom，thread=`duty_{pid}_{contact}` 按联系人持久）、移动端。Agent 收到临时消息后的行为协议：

| 判定 | 处置 |
|---|---|
| 只读咨询（"今天卖了多少"） | 直接答复，不建任务 |
| 涉及未来时点 / 需多步 / 需验收留痕（"明天把鸡蛋下架"） | **建任务**（source=user, provenance={kind: message, ref: 对话 thread}），答复"已排入任务列表" |
| 紧急且 T3/T4（"把 A 商品改价 59"） | 立即执行 + 留痕（run 即凭证），答复执行结果 |
| T1/T2 资金类 | **一律建任务走验收**，禁止消息内即时执行 |

值守渠道整合要点（现状已核实）：wecom 与 kf 均为**按联系人/客户持久 thread**（`duty_{pid}_{contact}` / `duty_{pid}_{external_userid}`），回复路由回原联系人（wecom `_send_reply`；kf 经 `_kf_routing` 反查 open_kfid 走 `servicer_send_reply`）——这是**对话语义的输出**；任务进展/验收通知是**任务语义的输出**（第 8 章），两通道并行不混用。

### 6.3 入口③：第三方系统事件

- **外部系统不派 Agent，只建任务**。**通道 = MCP 通知（既有体系，零新机制）**：
  mall MCP server 推送 `notifications/task_event`（params 契约 = {event_id, spec{title, project_id, ...}}，推送方必带全，引擎不做形状猜测）→
  evoloop MCP client 以通用事件 `MCP_SERVER_NOTIFICATION` 入总线 →
  `TaskEventSubscriber`（`app/domain/tasks/notification_subscriber.py`，对齐 `on_kf_new_message` 订阅模式）
  过滤 method → `ingest_event` 建任务（幂等 dedup 保留）。鉴权复用 MCP server 连接凭证，零新机制。
- **不建 HTTP webhook**：内嵌（桌面）模式 API 仅绑 loopback，远程源不可达；且会引入平行于 MCP 的第二套鉴权。
  full 模式未来确需 HTTP webhook 时，按 InputChannel 体系（web_input 同款）实现，现阶段不做。
- 处理链（引擎侧仅两件事）：MCP 通知 → 幂等去重（dedup_key = `{source}:{event_id}`）→ 建 Task 行。
  **事件→任务语义（如 order.paid → 发货确认）由项目侧推送方组装进 spec，引擎零业务词汇。**
- **微批聚合**：高频事件由推送方聚合后推送（引擎侧不做缓冲，保持系统只排队）。
- **消息型任务 vs 会话消息**：投诉工单 = 任务（要动作+验收）；客户聊天 = 会话（servicer 域 + kf SSE 推送既有）。双触发事件：建任务 + 客服通道自动回复。
- mall 侧接入（阶段五）：扩展 mall MCP server 的推送（对齐 `kf_new_message` 的 5s 检测先例），不动 mall PHP。

### 6.4 派生：Agent 提案（自排程闭环，本方案核心增量）

- 任一 run（wakeup / 消息会话 / 周期任务）中发现新待办 → `create Task(source=agent, provenance={kind: agent_run|patrol_run|message, ref: 任务/ thread id}, status=proposed)`；
- 提案含：依据（哪个任务/哪轮巡逻发现的）、建议分类/优先级/风险档、行动草案；
- T3/T4 提案可配置自动入列；T1/T2 必须 proposed → 用户确认；
- 闭环：`run → 发现 → 提案 → （确认）→ pending → 下一个 wakeup 消费`。**Agent 从此能给自己派活**；
- patrol 与 agent_run 派生分记 provenance：前者是系统化覆盖的产物（漏报=checklist 有洞，可修），后者是干活顺带发现（漏了正常）——看板可区分"站岗站出来的"与"干活撞见的"。

## 7. 计划与自检

### 7.1 计划生成

wakeup run 领取任务后，用 plan 工具（挂 task_id）生成执行计划。输入四要素：
1. 任务行本身（title / description / source_ref）；
2. 项目进展（此前相关任务与计划的结论、episodic 记忆）；
3. 知识库（运营 SOP、商品/店铺资料，经 skill 包与记忆系统注入）；
4. 业务规则（能力包 SOP 中的约束：如调价幅度 ≤15%、退款 T2 必须人工）。

计划不是任务拆步骤的机械动作，而是**带上下文的决策产物**——同一类任务在不同店铺状态下计划不同。

### 7.2 结构化自检（self_check）

- 每个计划**末步必须是验证步骤**（对齐 MCP 四件套 `verify_after` 语义）；
- 自检产出结构化 JSON（`self_check` 字段）：`{verdict: pass|deviation, checks: [{name, pass, evidence}], deviations: [...]}`，evidence 指向 MCP 查询回执（订单号/商品 id/配置快照）；
- 自检报告 = 验收的输入：用户点开任务即可核对检查点与证据，**不读话术**；
- verdict=deviation 时任务只能到 waiting_acceptance 并附偏差说明，不得自行判 accepted。

---

### 7.3 提示词层调整清单（已全部落地，结论存档）

四层结构：主人格（`main.txt`）+ 值守变体（`main.duty.txt`，客服硬限拆 `main.duty.customer.txt` 条件拼装——系统层按 `CUSTOMER_FACING_CHANNEL_NAMES` 判定）+ 域守则（`fragments/mall_ops.md`）+ 能力包 SOP。关键裁决：`main.txt:30` 非阻塞项协议改为"直接 create Task(source=agent, proposed)"（随 Task facade 落地）；`mall_ops.md` 写操作确认条款改为风险分档（T1/T2 确认、T3/T4 值守直执+留痕）；mall-refunds T1/T2 严格确认保留。

## 8. 验收流

- **风险分级**（继承 MCP 四件套标注，任务创建时由分类/模板推断，用户可改）：

| 档位 | 完结条件 |
|---|---|
| T1 资金 / T2 退款资金流 | self_checked → waiting_acceptance → **用户验收** → accepted |
| T3 可逆业务状态 / T4 低危内容 | self_checked → **自动 accepted**，事后抽查 |

- **rejected 回流**：验收不通过必填反馈 → 任务回 in_progress（或退回 proposed 重规划），feedback 附在 acceptance 里，下一轮计划必须响应；
- **验收通知**：waiting_acceptance 任务按现有通知通道提醒（站内 + 企微，渠道复用 duty 通知配置）；
- **验收交互闭环**（通知是单向的，必须定义动作在哪完成）：
  - 主路径：Web 任务列表验收区，点验收/驳回（驳回必填反馈）；
  - 副路径：企微值守会话回复验收指令（"验收 T-12" / "驳回 T-12 原因是…"）——Agent 收到后在任务系统落验收回执并回复确认；本质是 6.2 转化协议的一条例外：验收指令直接执行且 T4 留痕；
  - 值守渠道 `send_hitl_request` 为 no-op（`duty/base.py:298`）——验收呈现走"任务状态变化 + 通知"，不依赖渠道交互 UI；T1/T2 阻塞语义与 HITL 一致（车道锁等待，见 5.3）；
- 吞吐护栏：自动通过档保证 Agent 不被验收阻塞；T1/T2 阻塞语义与 HITL 一致（车道锁等待）。

---

## 9. 界面设计（无限画布主视图 + 手机端 + 零轮询数据流）

> 自 2026-09-21 起本章为本文档内嵌章节（原独立于 `docs/task-system-fullflow.md`，该文件已并入本文档并转为指针）。代码落点：`workbench/src/canvas/`。

### 9.1 形态定论：无限画布为主视图

**依据**：工作台的本质是 **Agent 向用户呈现"我在干什么"**——人参与极少，主体是 Agent 的工作现场。这个现场是空间性的：任务的产物形态异构（调研=报告卡、选品=可勾选方案卡、素材=图网格、文案=标题卖点排、投流=漏斗图、发布=平台状态 chips），任务关系是依赖连线（带产出语义标签）。列表行与结构化泳道承载不了异构产物；画布上**每类节点用专属布局**，连线+空间组织表达关系。执行时**视觉焦点自动跟随**（画布平移到当前节点、节点 busy 闪烁）——"Agent 告诉用户我在干什么"的最佳呈现，且拍板/仲裁卡内嵌在对应节点上。

> 曾对比过结构化泳道/焦点图（DOM+SVG 连线）——其信息架构（下述四问关系区）保留为画布抽屉内的关系组件；作为主视图，画布胜在：异构产物卡、焦点自动跟随、空间组织、以及未来产物密集场景（素材库/文案改稿）无需再换形态。实现参照 `demos/content-workbench`（tldraw + KIND 卡机制 + focus/fit 逻辑）。

### 9.2 桌面主视图：任务画布

```
┌─ 顶栏 ────────────────────────────────────────────────────┐
│ 阶段带：市场(3/3)→选品(⏸拍板)→供应商→定价→内容(0/3)→上架    │
│         →运营(0/4)→复盘    [状态灯：执行中 5/15 / 等待拍板]  │
├──────────────────────────────────────────────┬────────────┤
│                 任务画布（主视图）               │  右侧抽屉   │
│                                                │ (点节点滑出) │
│  [T1 报告卡] [T2 IP验证卡] [T3 盘点卡]           │            │
│        └──────┼───────┘                        │ 执行时间线   │
│         [T4 选品卡 ⏸ 拍板卡内嵌:方向①②③]        │ 评审动态    │
│           └──────┬──────┘                      │ 关系区(四问)│
│   [T5 供应商] [T6 定价矩阵] [T7 知识卡]           │ 产物详情    │
│              └→ [T8 素材图库卡(缩略图)]           │            │
│                    └→ [T9 文案卡]               │            │
│                         ↓                      │            │
│      [T10 商品卡] → [T11 笔记] [T12 漏斗卡]      │            │
│      （旁支卡灰显分区；血统徽标 💬🤖⛓ 在卡角）      │            │
└──────────────────────────────────────────────┴────────────┘
```

**画布要素**：

| 要素 | 设计 |
|---|---|
| 节点 | 异构产物卡（每类任务专属布局：报告摘要卡/方案勾选卡/图网格/漏斗图/发布状态 chips） |
| 连线 | 依赖链，边上挂产出语义标签（"产出：3 个 SKU 方向"） |
| 焦点自动跟随 | run 开始自动 pan 到当前节点；执行中 busy 闪烁；完成后变 ✓ 移动下一卡；拍板时停在节点上等 |
| 节点状态 | 状态即卡角：✓完成 / ⟳执行中 / ⏸等你拍板 / ○未解锁（灰）/ ⛔失败 |
| 拍板/仲裁/HITL | 内嵌在对应节点弹出（不弹独立页面） |
| 血统/旁支 | 卡角徽标 💬🤖⛓⏰；旁支提案灰显分置 |
| 左列任务列表 | 降级为索引/过滤入口（按阶段/状态筛选、定位到画布节点） |

**右侧抽屉（点节点滑出，单任务详情）**：

```
◆ 血统：来自对话「帮我巡检商城…」（锚点跳回产生消息）
◆ 上游：#T-4 ✓已完成 → 产出摘要（截取）
◆ 下游：#T-8 / #T-9（等本任务完成）
◆ 核验：监察评审（原对话）· 通过
──────────────────────────
计划（3/4，步骤列表）
执行时间线（工具调用/思考/产物）
产物预览（图缩略/文案卡/报告卡）
验收操作（signoff：批准/打回；评审中：评审动态；仲裁：重跑/取消/调整）
```

> 泳道方案的信息架构并入抽屉"关系区"——四问（因谁而生/输入是谁/产出喂谁/结果谁背书）在此逐条回答；画布是过程主视图，抽屉是单任务详情。四种关系的数据源：血统=`source_ref`、上游=`dependencies`、下游=依赖反查、核验=`acceptance.by`。

### 9.3 手机端

```
┌───────────────────────┐
│ 链路总览（竖向阶段流水） │ ← 8 段阶段 + 卡点/断点指示
│ 🔔 拍板：#T-4 选方向    │ ← 拍板卡（手机直接勾选/批准/打回）
│ ⚖️ 仲裁：#T-148        │
│ ✓ #T-1 完成            │
│ ⟳ #T-5 执行中          │
└───────────────────────┘
```

| 能力 | 设计 |
|---|---|
| 链路总览 | 阶段带竖版 + 当前焦点任务卡 |
| 拍板 | signoff 任务直接批准/驳回（调 accept/reject API） |
| HITL 审批 | 已有（hitl.request 卡） |
| 通知 | signoff/断链/24h 提醒（已接）；评审结果、任务完成推送待补 |

### 9.4 数据刷新模型（2026-09-21 定稿：零周期轮询）

| 视图 | 实际形态 | 数据 |
|---|---|---|
| 画布主视图 | `AutonomousDutyCanvasApp`（DutyCanvas / DutyNodeCard / DutyTopBar / DutyLeftSidebar / layoutEngine） | /tasks/queue + /tasks/queue/dashboard |
| 执行详情 | `detail/ExecutionPanel.tsx`：thread 时间线 / 计划步骤 / artifacts 预览 / HITL 卡 | /stream/thread/{id} |
| HITL 感知 | hitl-pending（waiting_acceptance/HumanRequest 聚合） | /tasks/queue/hitl-pending |
| 启停 | 全局总闸（DutyStartStopButton）+ 项目分闸（`PUT /projects/{id}/duty`）双闸 | customer_service_duty |

- SSE 主路径：`/stream/tasks`（task_taken / task_updated / hitl_created / hitl_resolved，`api/routes/stream.py:378`）与 `/stream/thread/{id}`（thread_updated，`stream.py:496`）→ 事件即 `invalidateQueries` 精准刷新；
- 断线对账：EventSource 原生重连 + `source.onopen` → 一次 invalidate 收敛断线窗口（不设 refetchInterval——曾以 60s/3s 轮询兜底，已全部拆除）；
- 窗口聚焦 refetch（TanStack 默认）为免费第三层。
- 目标不变：用户随时可答三问——**Agent 正在干什么、此前干了什么、还要干什么**。

---

## 10. 与现有代码的映射（改动清单）

### 10.1 前置收尾清单（todo/plan 统一的尾巴，先于阶段一）

> todo 域已退役、plan 已进默认面（agent_main.yaml），分裂脑已消除。以下 4 项是实测发现的残留，其中 #1 为本方案硬前提：

| # | 对象 | 问题 | 动作 |
|---|---|---|---|
| 1 | mall `.evoloop/capability_profiles.yaml:16` | `native_tools` 白名单仍含 `todo`（幽灵引用，装配器交集过滤静默忽略），且**无 `plan`** → mall_ops 内嵌 Agent 当前没有任何任务追踪工具，wakeup run 唤醒 prompt 指挥用 plan 会直接断链 | 白名单改 `[webfetch, websearch, plan, skill, question]` |
| 2 | `app/domain/planning/tools.py` | 旧入口 `create_plan` / `update_step_status` 仍被 `REGISTRY.scan("app.domain")` 自动注册，与 plan facade 平行（同表写入无分裂，但三入口混用、旧入口无 result 语义） | 删除旧工具，收敛为 facade 单入口 |
| 3 | mall `.evoloop/skills/haodanku/SKILL.md:62` | SOP 仍在教 Agent 调旧入口 `create_plan` / `update_step_status` | 改写为 plan facade 语义（`plan(action=...)`） |
| 4 | `app/domain/planning/facade_tool.py:136` | `update_step` 的 result 必填仅 docstring 约定，代码仍 `if result:` 宽松写入；断点续跑与查验视图的数据质量无保证 | completed 时服务端强校验 result（含长度上限约定，防小作文） |
| 5 | `infrastructure/scheduler/service.py:23`、`duty/scheduler.py` 队列注释 | "Huey periodic tick" / "Huey 单 worker 下 tick" 为过时错误注释（实际 tick 由 API 进程 asyncio 循环驱动，见 5.1），误导后续设计（本方案初稿即被误导） | 修正注释，与 main.py 实际机制对齐 |


> **执行状态（2026-09 已全部落地）**：
> #1 白名单已改 `[webfetch, websearch, plan, skill, question]`；#2 `planning/tools.py` 的 create_plan/update_step_status 已删除（analyze_feasibility 非分裂脑问题，保留待另行评估）；#3 haodanku SKILL.md 已改 facade 语义；#4 update_step 强校验已实现（completed 必填 result + 500 字符截断），新增 5 个单元测试全过（`tests/unit/domain/planning/test_plan_facade_update_step.py`）；#5 两处过时注释已修正，并在 main.py 固化"先 tick 后 sleep = 启动即补扫"语义注释。全程 ruff 0 error、ast 通过、planning 集成测试 3/3。

### 复用不动
- AutonomousTask / SchedulerService 既有职责（值守 wecom/kf、宏定时）
- Plan 工具本体（facade 已是唯一执行追踪入口）
- duty 护栏代码（认领推进 / 在飞 / 串行 / 硬超时）
- HITL 全链路、doom-loop、G4、ErrorEmitter、ContextTrimmer
- mall MCP 原子矩阵与四件套
- capability packages 装配机制（category 直接对齐域装配）

### 改造
| 对象 | 改动 |
|---|---|
| `Plan` 模型 | + task_id FK |
| `engine_scheduler_tick` | 扫描面扩展 project_tasks；认领推进语义平移 |
| `duty/base.py` business_poll_check | patrol 派发路径切换为 project_tasks 数据源；护栏保留 |
| `completion.py` 收尾管线 | + 「遗留步骤/新发现 → Task 提案」回写 |
| 能力包 | + 值守 wakeup 包（任务管理 SOP）；各业务包补 tasks 工具引用 |

### 新增（已实现修订 2026-09-21：实际落点与设计稿对照）
| 对象 | 实际位置（设计稿设想 → 实际落地） |
|---|---|
| ProjectTask 增量字段 alembic 迁移 | `app/models/project.py` 扩展（a7b3c9d1e5f7）✅ |
| Task facade（list/take/update_status/create/complete_check/submit_acceptance） | `app/domain/tasks/`（TaskQueueService + `tools/tasks_tool.py` 薄封装）——**未走** `core/project/tools.py` 扩展路线（该路线曾在设计期提出，实际落在了 domain/tasks/） |
| 调度派发（设计稿 ops_scheduler.py → **实际**） | `app/domain/tasks/runtime/supervisor.py` + `runtime/dispatcher.py`（单 drainer，无车道） |
| TaskEventSubscriber（MCP 通知 → 建任务） | `app/domain/tasks/notification_subscriber.py` ✅ 已落地 |
| 事件入口 HTTP 端点 | `POST /tasks/events/{source_system}`（验签 EVENT_INGEST_SECRET / dedup 幂等）✅ |
| 值守 wakeup 能力包 | mall 侧 `.evoloop/skills/`（域装配按 capability profile） |
| 巡逻 checklist 数据化 | `scripts/migrate_business_poll.py` → recurring 任务行（阶段三）✅ |

---

## 11. 迁移与灰度

1. **阶段〇（收尾，前置）✅ 已完成**：10.1 清单 5 项全部落地——mall 域白名单 `todo→plan`（硬前提，否则 wakeup run 无计划工具）、旧 plan 工具退役、haodanku SOP 语义修正、update_step result 强校验、调度相关过时注释修正。
2. **阶段一（地基）✅ 已完成（2026-09）**：ProjectTask 增量字段迁移 + Task facade 工具 + tick 扫描接入；事件入口（仅 mall 订单/售后两个模板事件，优先 MCP push 模式零侵入）；Plan.task_id 已落地：11 个队列字段 alembic 迁移（a7b3c9d1e5f7，SQLAlchemy 建表 introspection 验证）、Plan.task_id、`app/domain/tasks/`（TaskQueueService + tasks facade，domain scan 注册验证）、tick 车道合派（dispatch_due_task_lanes + task_wakeup.prompt.j2）、agent_main 默认面 +tasks（22 件套）；单测 10/10。**事件入口已落地：POST /tasks/events/{source_system}（验签 EVENT_INGEST_SECRET / dedup 幂等 / 胖 payload spec 建任务，引擎零业务语义；模板映射归 mall 项目侧）。**
3. **阶段二（闭环）✅ 已完成（2026-09，评审瘦身）**：核心认知——Agent 提案的关键不是机械件而是**提案区信噪比**（用户注意力预算 = 自排程闭环生命线）。落地：A 提案协议（main.txt 准入三问/四要素/查重/单 run ≤3 条/拒绝反馈可见）；B1 完结分流（self_checked 瞬态：T3/T4 → completed by=system:auto 可审计，T1/T2 → waiting_acceptance）；B2 执行权隔离（submit_acceptance/自我批准从 Agent 工具面移除，用户侧 /tasks/queue/* API 专属）。砍除：completion 未完成步骤转提案（与断点续跑冲突）、去重合并引擎强制（提示词+拒绝反馈替代）、run 限流代码（纪律归提示词）、SSE 通知（无界面期推迟）。
4. **阶段三（迁移）✅ 已完成（2026-09，无双轨一次性切换）**：迁移脚本 `scripts/migrate_business_poll.py`（幂等 dedup、--dry-run/--execute、checklist 数据化入 task_data）→ 6 条 patrol 任务行入库（orders 30min/refunds 60min/stock·member 120min/promotion·finance 240min，与原间隔一致）；B1 补 recurring 完结语义（self_checked → 回 pending，本轮报告入 task_data.last_result）；退役：存量 KIND_BUSINESS_POLL 触发行已停用、provision 不再 upsert、旧 prompt 已 enabled=false；域装配：`list_domains` 读项目侧声明，wakeup 派发注入 intent_hint（profile-first，修复 L0 ecommerce 误判）。测试 70 passed（含 recurring 多轮/幂等/checklist 映射/域声明）。**数据态补注（2026-09-21）**：开发库其后清空重建，6 条巡检以真实创建路径重新 seed（订单/售后 30min cron、库存/会员/营销/资金每日 cron，北京时间换算 UTC；`trigger_spec` 全为 croniter 格式），休眠态=双闸关闭，未激活。
5. **阶段四（界面）✅ 主体完成（2026-09，含全宽/启停修正）**：顶栏中央 Tabs（聊天对话 ⇄ 自主值守·实验，整页滑动）；自主值守 Dashboard 三栏联动——左列任务五分区（提案/队列/进行中/待验收/完成，行内确认/驳回/验收）、中列 KPI 五格（值守状态灯/工作时长/当前任务/今日·本周 Token）+ 当前计划步骤（实时）、右列执行过程流（thread 消息）、底部本周日历条带；详情抽屉（指令/自检报告/验收回执）；新建/编辑表单（一等列绑定）；实验性提示弹窗（一次性确认）；15s 轮询刷新（SSE task_updated 管线待接）。**布局：_layout isFullWidth 全宽路由（duty-autonomous 已列入）；值守启停=右上角启/停按钮**（toggle 全局 customer_service_duty.enabled，对齐设置页总闸；KPI 上方右侧）。数据源：GET /tasks/queue/dashboard 聚合端点（agent_activities 既有 Token 采集直接聚合，零新基建）。
6. **阶段五（扩展）**：CRM / 供应链等外部系统接入；LLM 分诊通道；微批调优。

灰度验收指标：
- 双轨期同类巡检的提案一致率 ≥ 阈值；
- 空闲时段零 wakeup run（tick 空转率 100%）；
- T1/T2 任务 100% 走验收；rejected 回流任务的新计划引用了 feedback；
- 断点续跑：kill -9 后下轮 wakeup 无任务重复执行（dedup + 认领推进验证）。

---

## 12. 开放问题（2026-09-21 更新）

1. ~~OpsTask 归属~~ **已消解**：复用既有 project_tasks。
2. **webhook 鉴权** → **部分消解**：事件入口走 `POST /tasks/events/{source_system}` 验签 `EVENT_INGEST_SECRET`；外部第三方是否再分通道，接入时再定。
3. ~~车道数上限~~ **已消解**：车道未落地（串行 drain），category 只是排序+装配键。
4. **微批窗口**：固定 5 分钟 vs 按事件类型 SLA 自适应（发货 5min / 入驻审核即时）？
5. **验收通知升级**：waiting_acceptance 堆积超阈值的升级策略（提醒 → 短信 → 自动降级暂停）？
6. **巡逻成本**：真实数据点（2026-09-21 实测）：单轮深度巡检 run 上下文可达 ~57k input tokens；全量 LLM 巡检的成本 vs 部分检查项代码化（纯 SQL 判定阈值，仅异常时起 LLM）待权衡。
7. ~~跨项目车道并行~~ **已消解**：无车道，全局串行；多项目隔离沿用 project_id。
8. **审计**：T1/T2 执行留痕是否直接复用项目侧操作日志（如 mall `oms_list_op_logs`），还是 Task 侧再存一层回执。

---

## 13. 断层记录（活工单，按编号引用；自 task-system-fullflow.md 并入 2026-09-21）

### 体验层（桌面）

| # | 断层 | 状态 |
|---|---|---|
| ~~D1~~ | ~~画布主视图未实施~~ | **已闭环（2026-09-21）**：`workbench/src/canvas/` 已实施为唯一主视图，焦点自动跟随已实现（`DutyCanvas.tsx` autoFollow/flyToCard） |
| D2 | 拍板"选择"语义 | 画布已承载单选拍板（AutonomousDutyCanvasApp 自述闭环 D2；**逐项验收待做**） |
| D3 | 仲裁结构化三键 | 画布已承载（同上；**逐项验收待做**） |
| D4 | signoff 卡内嵌拍板对象（产出摘要/方案全文） | 未闭环 |
| D5 | 任务卡与产物割裂 | 画布已承载产物卡；ExecutionPanel 另有 artifacts 预览 |

### 体验层（手机）

| # | 断层 | 状态 |
|---|---|---|
| M1 | signoff 推送只能看，无手机端批准/驳回动作 | 未闭环 |
| M2 | 无链路进度页（竖向阶段带 + 断点指示） | 未闭环 |
| M3 | 评审结果/任务完成无推送（signoff/断链/提醒已接） | 未闭环 |

### 流程层

| # | 断层 | 状态 |
|---|---|---|
| F1 | HITL 挂起 24h 超时 → 回队**从头重跑**（非恢复挂起点） | 未闭环（用户应答路径有 resume；仅超时路径重跑） |
| F2 | 合成消息不含 artifacts 链接，评审者缺产物线索 | 未闭环 |
| F3 | 评审核验事实随环境漂移（执行时≠评审时），评审意见未带环境/时间快照 | 未闭环 |
| F4 | 上游 failed 后下游无 blocked 终态标记 | **部分闭环**：断链已在状态条可见 + 可重跑（阶段六）；自动重试策略仍缺 |
| F5 | signoff 人工打回次数无上限（刻意设计），界面缺"已打回 N 次"提示 | 未闭环 |
| F6 | 原对话评审结论消息与看板任务状态无互链（消息→任务反查） | 未闭环 |

---

## 附：术语表

| 术语 | 含义 |
|---|---|
| Task（ProjectTask） | 任务实体（复用既有表 + 增量字段），任务队列 SSOT。**无 Ops 前缀**——任务就任务，商城只是一个项目 |
| ~~车道（lane）~~ | **未落地概念（2026-09-21 校订）**：设计的 category 并行车道未实现——category 实际只作派发排序键 + 域装配 hint；执行为全局串行 drain |
| wakeup run | supervisor 派发触发的**自主值守** Agent run，每轮消费恰好一个到期任务（人格走 main.duty.txt 变体 + 唤醒 prompt） |
| patrol | （沿用叫法）周期检查类任务，无类型字段；发现事项按风险门控当场处理或建提案 |
| 自主值守 | 原"客服值守"的升级形态：任务值守 + 消息值守 + 周期巡逻统一由 Agent 承担；回复硬限按渠道判定 |
| ~~同车道合派~~ | **未实现**（随车道一起撤回）；实际为串行逐任务派发 |
| 微批聚合 | 事件入口侧策略：高频外部事件按时间窗聚合成一条批次任务（不是任务拆分，是任务创建的粒度控制） |
| ~~事件直派~~ | **未实现插队通道**；紧急任务随下一拍 drain（事件唤醒 ≤60s） |
| 派发即认领 | 系统侧认领原语：派发前落 in_progress + last_thread_id + dispatch_count++（护栏加固，阶段七） |
| 项目分闸 | customer_service_duty.enabled 的 per-project opt-in 闸：关 = 到期任务挂起不派发；任务的"不激活"开关 |
| 四件套 | mall MCP 写工具标注：`[risk][confirm][read_before][verify_after]` |

---

## 阶段六（真实链路 + 事件驱动）✅ 当前态（2026-09-18）

### 派发架构（Codex 接线 + 评审收敛后的终态）
- **单 drainer**：`domain/tasks/runtime/supervisor.py`（事件驱动 + 60s 兜底）→ `dispatcher.dispatch_due_tasks` 串行 drain——**scheduler 旧 tick 已不再派发 project_tasks**（只剩 autonomous_tasks 纯定时器职责），无双 drainer。
- **真实执行链**：`EvoloopAgentRuntimeAdapter.run` → `dispatch_agent_run`（注入 `source_task_id` 进 ContextManager）→ `run_agent_background`（ReAct 真实 LLM + 真实工具）——mockLLM 仅存于 docstring DI 示例与 `scripts/mock_llm_server.py`（测试资产）。
- **工作流体系**：`task_workflows` 表（goal/inputs 数据层）+ `roles.py` 角色注册表（stage/system_prompt/output_artifact_type/allowed_packages）+ `task_artifacts` 表（产物权威源）+ 依赖链（dependencies 全 completed 才 ready）。
- **失败语义**：`failed → pending/cancelled` 状态机放开（人工重跑回队）；`NON_RETRYABLE_ERROR_MARKERS`（DataInspectionFailed/model parameter/invalid_request_error）→ 直接终态不烧重试；`GET /queue/{id}/rerun`（仅 failed 可重跑，409 守卫）。

### 前端（事件驱动 + 真实数据形态）
- **SSE**：`/api/v1/stream/tasks`（tasks:all:events）已接——`task_taken` 事件即时驱动"正在执行"状态条（零轮询延迟），终态事件回落；`LIVE·SSE` 连接灯。列表/计划/执行由事件触发精准刷新。
- **解析层**：`Duty/parse.ts` 纯函数（stripMcpRepr/textOf/toolNameOf/classify）+ 16 项单测（真实消息样例：MCP repr 剥壳/块数组/JSON 格式化/category 优先分类）。
- **数据对齐**：`/tasks/queue` items 补 created_at/updated_at/dependencies/elapsed_sec（thread 首末消息 span）/project_id/artifacts 内联；任务卡显示创建/完成时间与进行中运行时长（分钟粒度 memo，脱离秒级全页重渲）。
- **交互不变式**：右列详情永远跟随左列 Tab；跨 Tab 仅两个入口且自动带跳（需要你处理点击 / 提案确认落位）；决策统一在右列详情卡（队列卡纯选择）。

### 已知边界（下一步，2026-09-21 更新）
- ~~thread 级新消息/plan 步骤推进仍 5s 轮询（thread SSE 待接）~~ **已闭环**：thread SSE 已接（`/api/v1/stream/thread/{id}`，`api/routes/stream.py:496`），全部 `refetchInterval` 已拆除（SSE 事件 + onopen 重连对账 + 窗口聚焦 refetch 三层，零周期轮询）
- failed 依赖链的"阻塞"已在状态条可见 + 可重跑，但无自动重试策略（blocked → notify 运营）
- AutonomousDutyPage/ExecutionPanel 拆分（Codex 停改后可安全执行）
- 内容审查（DataInspectionFailed）是模型服务侧行为：换模型/改写文案/平台侧调整
- 远程 MCP server（evoloop.cn capability-matrix SSE）出现 ExceptionGroup 断连告警（2026-09-21 观测）；商城工具走本地 capability-matrix-mcp 不受影响，远程面可用性另行排查

---

## 阶段七（派发护栏加固 + 值守实链路验证）✅ 已完成（2026-09-21）

> 本轮为真实链路实测驱动的护栏加固，全部改动附 `tests/unit/domain/tasks/` 回归（144 passed）。

1. **派发即认领（one-shot claim-then-persist）**：`dispatch_due_tasks` 派发前系统侧原子认领（`claim_for_dispatch`：pending→in_progress + last_thread_id + `task_data.dispatch_count++`），`DispatchStatus.FAILED`/派发异常回滚 pending——修复"run 完成 × 任务未推进"紧派发环（实测：探针任务未调 tasks 工具 → ≥12 次重复派发烧 LLM）。`take_task` 幂等化（同线程重复 take 视为已绑定）。
2. **派发熔断**：`DISPATCH_CLAIM_CIRCUIT_LIMIT=5`，认领次数达阈值仍未推进终态 → 强制 failed（实测曾以 ~10s/次 烧 ~16 万 input tokens 的环，构造性关断）。
3. **recurring next_run_at 门控修复**：见 3.2 已实现修订；存量测试断言同步修正。
4. **stopping 僵尸判死**：`reconciler.py` 判死查询扩 RUNNING+STOPPING（事故：急停后重启，4 条任务永久悬挂 in_progress）。
5. **前端零轮询**：拆除 AutonomousDutyPage 60s 与 ExecutionPanel 两处 3s `refetchInterval`，`source.onopen` 重连对账接线（§9）。
6. **运维事故记录（环境层，非代码）**：mall 侧 MCP 服务（PHP 长驻进程，`member-center/backend/mcp-server/server.php`，监听 9301 经 nginx 9003 反代）自周五未重启，其 MySQL 连接被 wait_timeout 掐死且 2006 后不自愈 → 值守巡检报 "MySQL server has gone away" ×4 → Agent 按纪律创建提案任务（异常→提案闭环首次真实运行）→ 重启服务恢复。**教训：值守依赖的外部服务需要连接自愈或纳入值守巡检本身。**

---

## 阶段八（全局设计收敛）✅ 已完成（2026-09-23）

> 源于 2026-09-23 全维度审计（结构/流程/逻辑/页面/状态），本节为**新契约权威**——与上文冲突处以本节为准。全程 `tests/unit` 1806 passed 回归。

### 八.1 数据模型：task_data 拆解为一等列（审计 A1 根治）

- 迁移 `c4f7a1b9e2d3`：`title/priority/category/tags/dependencies/acceptance_criteria/workflow_id/dispatch_count/last_result/last_error/review_pending/workflow_retry_count/version` 全部提列 + 回填；`task_no` 去双写。
- **category 筛选/排序进 SQL**（`list_tasks` 白名单过滤 + `_queue_ordering()` CASE 表达式），不再内存过滤排序。
- 入参校验白名单化：priority（urgent/high/medium/low）、risk（T1-T4）、type（once/recurring）、source（user/agent/external）、category（≤100 字符）。
- **并发收敛**：`(project_id, task_no)` 唯一索引（迁移+ORM 双落），`create_task` 捕获 IntegrityError 重试（≤3 轮）；dedup 并发冲突回读已有任务幂等返回（不再向上炸异常）。

### 八.2 状态机加固：version 乐观锁 + 执行权归属 + fail-closed

- **version 乐观锁**贯穿 take/claim/advance/acceptance/requeue/edit（`WHERE version=?`，旧 run 覆盖新 run 被构造性阻断）。
- **thread 执行权**：`advance_task(thread_id=…)`，任务绑定 th-1 后 th-2 推进被拒（tasks 工具已接线）。
- **fail-closed 三则**：external 任务 → proposed（需用户确认，不再直接 pending）；缺 risk_level 的 one-shot self_check → waiting_acceptance（不再默认 T3 自动完成）；accept 必须有 result（完成必留痕）。
- **recurring 语义修正**：轮次完成优先回队（risk 闸门在每轮动作的 G4/HITL 层）——否则用户 accept 会把 completed 写成终态、巡检循环死亡。
- `edit_task`：cancel 服务端联动 `stop_agent`；新增 `dependencies` 替换式更新 + **服务端 DAG 校验**（去重/自依赖/存在性/同项目/环检测——画布连线的前端拓扑检查只是体验层）。

### 八.3 task_runs：任务与运行分离（过程记录层）

- 新表 `task_runs`（迁移 `d8e2f4b6a9c1`）：每次派发尝试一行（attempt/线程/终态/失败原因/结果摘要）。
- **裁决：不参与状态机判定**（任务态唯一权威 = `status` + version 锁；判死读 AgentActivity）——run 行是审计/观测层，"跑过几轮、每轮结果"不再是单行覆盖态。
- 写入点内聚 TaskQueueService：claim 开行 → advance/requeue/release 终态化。队列 API 每任务内联最近 5 次 attempt。

### 八.4 三套任务系统收敛为单一 SSOT

- `/api/v1/tasks/*` 只剩队列面（tasks_queue.py）；**EvoCloud 代理迁至 `/api/v1/evocloud/tasks/*`**（云透传契约保留，不再与本地任务同前缀）。
- **subtasks API 全退役**（路由/schemas/集成测试删除，前端/移动端零调用实证）；`subtask_service.py` + 旧工具岛（create_project_task(s)/create_task_with_subtasks/update_task_completion/get_next_executable_task/list_project_tasks）+ `REGISTRY.scan("app.core.project.tools")` 全部删除。
- 队列 API 请求体强类型（`TaskCreateRequest`/`TaskEditRequest` Pydantic 枚举），非法值 422。

### 八.5 多租户隔离（审计 P0 补齐）

- `artifacts`/`rerun` 补 CurrentUser + 归属 404；`hitl-pending` fail-closed 成员过滤（无法归属的请求不暴露）。
- `dashboard`/`list_queue` 无项目时按成员归属 SQL 过滤（`_member_task_filter`：member_id 列 ∪ Repository 项目归属）；"跨成员聚合"已知缺口测试翻转为隔离断言。
- SSE `/stream/tasks` 多租户下强制 project_id（全局任务事件流跨成员泄露封死）。

### 八.6 运行时修复

- **评审闸门不放水**：reviewer 派发失败从"自动验收"改为保持 waiting_acceptance（30min 评审超时兜底收敛，空结论=不通过）。
- **HITL 24h 过期接线**：`reconcile_stranded` 先过期（默认拒绝）再算豁免集，同轮回收挂起任务。
- **workflow 恢复缺口（审计 F-05）**：reconciler 三处 gate（HITL 豁免/判死/回队）从 `wakeup_` 扩为 `wakeup_`+`agent_`——workflow 阶段 run 崩溃后不再永久悬挂。
- **HITL 事件路由**：hitl_created/resolved 从只发全局频道改为同发项目频道（按值守线程前缀解析 pid）——项目级订阅实时可见。
- wakeup run 注册进 `agent_run_registry`（30min 硬截止真正可取消）。

### 八.7 前端对齐（页面状态 = 后端事实）

- **鉴权双通道**：手写 TasksQueueApi 接 `OpenAPI.TOKEN`（Bearer+Cookie）；thread SSE token 走 query（同 ChatConnection）。
- **提案驳回调对接口**（proposed → cancel 语义；acceptance reject 只接受 waiting_acceptance）。
- liveRun 残留修复（终态清除认 status 不认事件名）；失败详情新增"重新执行"（rerun）；评审中任务不再误开人工验收按钮（review_pending → 只读横幅）。
- cancelled 全呈现链（TaskRow/节点卡/详情 pill + 虚线样式）；队列分页（useInfiniteQuery + 加载更多，>50 条不再静默消失）；API 失败显错误态+重试（不再伪装空队列）。
- **画布连线持久化**（乐观更新 + 落库 + 失败回滚）；全屏详情页自渲染 HITL 审批卡；节点卡 N+1 修复（仅活任务拉计划）。
- **零周期轮询完整兑现**：ReviewProgressCard 5s 轮询重写为 query + origin 线程 SSE；死代码清理（DutyTopBar/DutyLeftSidebar/演示模拟链/伪 KPI 全删）。

### 八.8 裁决记录（不做，防过度工程）

| 项 | 裁决 | 理由 |
|---|---|---|
| outbox 事件表 | **不做** | 事件本就是加速器而非事实源（设计原则 §9.4），三层对账（SSE onopen / 60s 兜底 / 窗口聚焦）已覆盖丢失窗口；outbox 换来的是事务复杂度 |
| `customer_service_duty` 键更名 | **不做** | 25 处后端引用 + API 契约 + 持久化配置（systemconfig/project.json）长尾，纯命名收益不抵回归面；语义以注释指明 |
| 车道并行 / 分布式 lease | 维持不做 | 单进程串行 drain 是护栏等价前提；多 worker 部署需 `WORKERS=1`（部署层约束） |

### 八.9 部署层修复（2026-09-23 补）

- **deploy.sh 迁移命令**：`bin/migrate.py`（不存在的文件名）→ `bin/migrate`，并移除 `|| echo` 失败吞噬——迁移失败现在中止部署而非伪装成功。
- **HOST 守卫冲突**：`main.py` lifespan 的 loopback 强制与生产 `HOST=0.0.0.0` 直接冲突（启动即炸）。新增显式豁免 `ALLOW_REMOTE_BIND=1`（默认仍 fail-closed）；语音路由的逐请求 loopback 守卫（`routing/deps.py` 403/4403）不依赖绑定地址，防御纵深不因豁免失效。`.env.prod.*` 已补该开关。
- **遗留待运维决策**：`WORKERS=4` 与进程内单 supervisor 矛盾——多 worker 下 supervisor 重复派发（in-flight 状态是进程内存态）。要么生产 `WORKERS=1`（最简），要么做 DB lease 选主（未实施）；`.env.prod` 凭据轮换同待运维。
