/* ==========================================================================
   EvoLoop 自主值守工作台 · 核心统一数据类型契约 (core/types.ts)
   ========================================================================== */

/* Shared view types for the duty workbench panels */
export interface Attachment {
  type: "image" | "video" | "file"
  label: string
  w: number
  h: number
  duration?: number
  hue: number
}

export interface PlanStep {
  id?: string
  title?: string
  status?: string
}

export interface ArtifactView {
  id?: string
  stage?: string
  type?: string
  summary: string
  data?: unknown
}

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

/* 选项勾选回流 */
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
  tool?: string
  toolArgs?: unknown
  toolOutput?: unknown
  status?: "pending" | "running" | "done" | "failed"
  thinkingSnippet?: string
  durationSec?: number
}

/* 人工验收签收门禁 */
export interface SignoffSpec {
  status: "pending" | "approved" | "rejected"
  reviewerRole: "owner" | "admin" | "inspector"
  reviewedAt?: string
  reviewNotes?: string
  grantMode?: "once" | "always"
  options?: ChoiceOption[]
  rejectCount?: number
  requiresHuman?: boolean
  pickedIndex?: number
  lastFeedback?: string
}

/* 资金与高危门禁审批 */
export interface HitlSpec {
  status?: "pending" | "approved" | "rejected"
  scope?: string
  grantMode?: "once" | "always"
  approvedAt?: string
  approvedBy?: string
  pending?: boolean
  requestId?: string
  action?: string
  description?: string
}

/* 交互式人机协同请求 (HITL Request) */
export interface HumanRequestSpec {
  id?: string
  requestId?: string
  type: "text" | "choice" | "multi_choice" | "confirmation" | "acceptance" | string
  description?: string
  prompt?: string
  context?: string | null
  options?: string[]
  status: "pending" | "resolved" | "cancelled" | "waiting_human" | string
  submittedAt?: string
  response?: unknown
  decision?: unknown
}

/* 断链仲裁规格 */
export interface ArbitrationSpec {
  status: "needed" | "resolved"
  failedTaskTitle: string
  options: {
    key: "retry_upstream" | "cancel_downstream" | "reopen_modified"
    label: string
    hint: string
  }[]
  picked?: string
  resolvedAt?: string
}

/* 核心值守任务主实体 */
export interface DutyTask {
  id: string
  taskNo: number
  title: string
  description?: string
  category: "research" | "creation" | "analysis" | "delivery" | "inspection" | string
  status: DutyTaskStatus
  priority: TaskPriority
  riskLevel: TaskRiskLevel
  source: ProvenanceKind
  dependencies: string[]
  progress?: number
  etaSeconds?: number

  // 画布坐标与尺寸
  x: number
  y: number
  w: number
  h?: number

  stage?: string
  provenance: FourQuestions
  fourQuestions?: FourQuestions
  steps?: ExecutionStep[]
  artifact?: DutyArtifact
  signoff?: SignoffSpec
  hitl?: HitlSpec
  humanRequest?: HumanRequestSpec
  arbitration?: ArbitrationSpec

  self_check?: {
    verdict: "passed" | "failed" | "pending"
    notes?: string
    rulesCount?: number
    passedCount?: number
  }

  run?: unknown
  lastThreadId?: string | null
  projectId?: number | null
  rawQueueTask?: unknown
}

export interface DutyEdge {
  from: string
  to: string
  payloadLabel: string
}

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

export interface CanvasViewport {
  x: number
  y: number
  k: number
}

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
