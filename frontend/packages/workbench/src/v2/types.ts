/* ==========================================================================
   EvoLoop 自主值守工作台 · 无限画布模式核心契约 (types.ts)
   对齐 evoloop/frontend/packages/desktop/src/lib/tasksQueueApi.ts
   包含通用任务模型、生命周期、四问一屏、执行时序与异构产物
   ========================================================================== */

export type DutyTaskStatus =
  | "pending"             // 待执行
  | "in_progress"         // 进行中 (Agent 现场执行)
  | "proposed"            // Agent 主动提案 (待人确认)
  | "waiting_acceptance"  // 待验收 / 待商业拍板
  | "confirm"             // 待安全审批 / 资金门禁
  | "completed"           // 已完成 / 监察评审通过
  | "failed"              // 执行失败 / 触发仲裁
  | "blocked"             // 上游断链阻塞
  | "cancelled"           // 已取消

export type TaskPriority = "low" | "medium" | "high" | "urgent"
export type TaskRiskLevel = "T1" | "T2" | "T3" | "T4"
export type ProvenanceKind = "chat" | "agent_proposal" | "cron" | "chain" | "manual"

/* 选项勾选回流 (闭环 D2) */
export interface ChoiceOption {
  label: string
  note?: string
  margin?: string
  risk?: string
  picked?: boolean
}

/* 四问关系区：一屏回答 (Four Questions Architecture) */
export interface FourQuestions {
  sourceRef: string          // 💬 因谁而生（对话锚点/周期巡检/Agent提案）
  upstreamSummary: string    // ⛓ 输入是谁（上游产出 payload 摘要注入）
  downstreamTargets: string[]// 🚀 产出喂谁（下游拓扑解锁任务）
  endorsement: string        // 🛡 结果谁背书（监察评审/系统/人拍板）
  originMessageId?: string
}

/* 异构交付产物模型 */
export interface DutyArtifact {
  id: string
  type: "choice" | "matrix" | "gallery" | "funnel" | "report" | "copy" | "json"
  title: string
  summary: string
  data?: unknown
  images?: { id: string; label: string; hue: number }[]
  matrixData?: { tier: string; cost: string; price: string; margin: string; note: string }[]
  funnel?: { label: string; value: string; pct: number }[]
  options?: ChoiceOption[]
  body?: string
}

/* 执行步骤与 Agent 深度思考 */
export interface ExecutionStep {
  label: string
  detail?: string
  tool?: string          // MCP 工具名称，如 "mall.query_goods"
  thought?: string       // Agent 内部推理与思考片段
  durationMs?: number
  status?: "done" | "running" | "pending" | "failed"
}

/* 商业决策拍板数据 */
export interface SignoffSpec {
  prompt: string
  options: ChoiceOption[]
  pickedIndex: number
  rejectCount: number    // 已打回 N 次计数（闭环 F5）
  lastFeedback?: string
  requiresHuman: boolean
}

/* 人工仲裁三键控制模型 (闭环 D3, F4) */
export interface ArbitrationSpec {
  triggeredBy: string
  reason: string
  upstreamTaskId?: string
  downstreamTaskIds?: string[]
}

/* HITL 资金与高危写操作安全门禁 (闭环 D5) */
export interface HitlSpec {
  pending: boolean
  requestId?: string
  action: string
  description: string
  budget?: string
}

/* 对齐 evoloop/frontend 聊天界面的 HumanRequest 标准模型 */
export interface HumanRequestSpec {
  id: string
  type:
    | "approval"       // 4 级高危治理：取消 / 拒绝 / 仅本次 / 总是允许
    | "choice"         // 单选 + 每次必带自定义输入
    | "multi_choice"   // 多选 + 自定义输入
    | "confirmation"   // Yes / No 确认
    | "text"           // 澄清与补充文本输入
    | "proposal"       // Agent 主动提案：确认加入队列 vs 驳回修正
    | "acceptance"     // 成果验收：验收通过 vs 打回重做 (带反馈)
  prompt: string
  options?: string[]
  context?: string     // 结构化上下文（风险等级/操作行为/资源/预算）
  status?: "waiting_human" | "completed" | "cancelled" | "rejected"
  decision?: {
    action?: string
    grantMode?: "once" | "always"
    feedback?: string
    selected?: string[]
    value?: string
    timestamp?: string
  }
}

/* 核心通用任务模型 (QueueTask) */
export interface DutyTask {
  id: string
  taskNo: number
  title: string
  description?: string
  category: string
  status: DutyTaskStatus
  priority: TaskPriority
  riskLevel: TaskRiskLevel
  source: ProvenanceKind
  provenance: FourQuestions
  dependencies: string[]      // 上游依赖任务 ID 列表
  stage: string               // 阶段或拓扑层级标签

  // 画布空间坐标 (由通用拓扑引擎计算或覆盖)
  x: number
  y: number
  w: number
  h?: number

  // 执行与时序
  run?: {
    threadId: string
    llmCalls: number
    inputTokens: number
    outputTokens: number
    toolErrors: number
  }
  steps: ExecutionStep[]

  // 异构产物
  artifact?: DutyArtifact

  // 门禁控制与人在回路
  signoff?: SignoffSpec
  hitl?: HitlSpec
  humanRequest?: HumanRequestSpec
  arbitration?: ArbitrationSpec
}

/* 拓扑依赖连线 (带语义产出标签) */
export interface DutyEdge {
  from: string
  to: string
  payloadLabel: string        // 边上的产出语义标签，如 "产出: 3个SKU方向"
}

/* 手机端推送通知 (闭环 M3) */
export interface DutyNotification {
  id: string
  time: string
  taskId: string
  taskNo: number
  type: "signoff" | "arbitration" | "completed" | "blocked" | "hitl"
  title: string
  content: string
  read: boolean
}

/* 画布视口状态 */
export interface CanvasViewport {
  x: number
  y: number
  k: number                   // 缩放比例 (0.2 ~ 2.4)
}

/* 顶栏 KPI 指标 */
export interface DashboardKPIs {
  dutyState: "busy" | "idle" | "paused"
  tokenToday: { input: number; output: number; calls: number }
  taskCounts: {
    total: number
    inProgress: number
    needsYou: number
    completed: number
  }
}
