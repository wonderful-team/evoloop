/* ==========================================================================
   EvoLoop 自主值守工作台 · 任务数据适配器 (taskAdapter.ts)
   负责将后端 QueueTask / ProjectTask 实时转换为无限画布所消费的 DutyTask 模型：
   - 动态解析 DAG 依赖网络 (dependencies)
   - 动态双向求解「四问」全景：因谁而生 / 输入是谁 / 产出喂谁 / 结果谁背书
   - 产物映射与人机回路（拍板 / 审批）转换
   ========================================================================== */

import type {
    DutyArtifact,
    DutyTask,
    DutyTaskStatus,
    FourQuestions,
    ProvenanceKind,
    SignoffSpec,
    TaskPriority,
    TaskRiskLevel,
} from "./types"
import type {QueueArtifact, QueueTask} from "@/lib/tasksQueueApi"

/**
 * 转换单个产物模型
 */
export function adaptQueueArtifactToDutyArtifact(
  art: QueueArtifact,
): DutyArtifact {
  let artType: DutyArtifact["type"] = "report"
  const rawType = (art.type || "").toLowerCase()

  if (rawType.includes("choice") || rawType.includes("option")) {
    artType = "choice"
  } else if (rawType.includes("matrix") || rawType.includes("pricing")) {
    artType = "matrix"
  } else if (rawType.includes("gallery") || rawType.includes("image")) {
    artType = "gallery"
  } else if (rawType.includes("funnel")) {
    artType = "funnel"
  } else if (rawType.includes("copy") || rawType.includes("text")) {
    artType = "copy"
  } else if (rawType.includes("json")) {
    artType = "json"
  }

  const data = art.data as Record<string, unknown> | null

  return {
    id: art.id,
    type: artType,
    title: art.stage ? `${art.stage} 交付物` : `产物 v${art.version || 1}`,
    summary: art.summary || "Agent 执行产出数据",
    data: art.data,
    body: typeof data?.content === "string" ? data.content : undefined,
  }
}

/**
 * 将来源映射为标准 ProvenanceKind
 */
function mapSourceKind(
  source: string,
  sourceRef: unknown,
  triggerSpec?: string | null,
): ProvenanceKind {
  // 优先级（强→弱）：
  // 1) trigger_spec 非空 = recurring → 周期巡检（无论谁建的）
  // 2) source=agent → Agent 提案（即使绑定 origin，提案身份优先于链路）
  // 3) source_ref.kind：message=对话产生 / event=外部事件 / chain=依赖派生
  // 4) source 兜底：external=外部事件 / user=手动创建
  if (triggerSpec) return "cron"
  if (source === "agent") return "agent_proposal"
  const ref =
    sourceRef && typeof sourceRef === "object"
      ? (sourceRef as { kind?: string })
      : null
  if (ref?.kind === "chain") return "chain"
  if (ref?.kind === "event") return "event"
  if (ref?.kind === "message") return "chat"
  // 周期流水线阶段任务（WorkflowService.spawn_round 派发）→ 周期巡检语义
  if (ref?.kind === "workflow_round") return "cron"
  if (source === "external") return "event"
  return "manual"
}

/**
 * 状态映射
 */
function mapStatus(status: string): DutyTaskStatus {
  const s = status.toLowerCase()
  switch (s) {
    case "in_progress":
      return "in_progress"
    case "waiting_acceptance":
      return "waiting_acceptance"
    case "completed":
      return "completed"
    case "failed":
      return "failed"
    case "cancelled":
      return "cancelled"
    case "blocked":
      return "blocked"
    case "proposed":
      return "proposed"
    case "pending":
    default:
      return "pending"
  }
}

/**
 * 构造四问全景关系
 */
function buildFourQuestions(
  current: QueueTask,
  allTasksMap: Map<string, QueueTask>,
  downstreamMap: Map<string, string[]>,
): FourQuestions {
  // 1. 💬 因谁而生（血统）
  let sourceRef = "自主循环派生"
  // 周期流水线阶段：回溯所属流水线（名 · 轮次 · 阶段键）
  const wfRaw = current as {
    workflow_name?: string | null
    provenance?: { sourceRef?: { round?: number; stage?: string } }
  }
  if (
    wfRaw.workflow_name &&
    (current as { provenance?: { sourceRef?: { round?: number } } }).provenance
      ?.sourceRef &&
    typeof (current as { provenance?: { sourceRef?: { round?: number } } })
      .provenance?.sourceRef === "object"
  ) {
    const rd = (current.provenance!.sourceRef as { round?: number }).round
    const st = (current.provenance!.sourceRef as { stage?: string }).stage
    sourceRef = `周期流水线「${wfRaw.workflow_name}」第 ${rd ?? "?"} 轮${st ? ` · 阶段 ${st}` : ""}`
  }
  const rawRef = current.provenance?.sourceRef || (current as { source_ref?: unknown }).source_ref
  if (rawRef) {
    if (typeof rawRef === "object" && (rawRef as { ref?: string }).ref) {
      sourceRef = (rawRef as { ref: string }).ref
    } else if (typeof rawRef === "string") {
      sourceRef = rawRef
    }
  } else if (current.source === "user") {
    sourceRef = "用户指令指派"
  } else if (current.source === "chat") {
    sourceRef = "对话上下文派生"
  } else if (current.source === "cron") {
    sourceRef = "周期巡检触发"
  }

  // 2. ⛓ 输入是谁（上游）
  const deps = current.dependencies || []
  let upstreamSummary = "根任务 · 独立启动"
  if (deps.length > 0) {
    const upstreamLabels = deps.map((depId) => {
      const parent = allTasksMap.get(depId)
      if (parent) {
        return `#T-${parent.task_no ?? "?"} ${parent.title || ""}`.trim()
      }
      return `#T-${depId.slice(0, 4)}`
    })
    upstreamSummary = upstreamLabels.join(" · ")
  }

  // 3. 🚀 产出喂谁（下游）
  const downIds = downstreamMap.get(current.id) || []
  let downstreamTargets: string[] = []
  if (downIds.length > 0) {
    downstreamTargets = downIds.map((downId) => {
      const child = allTasksMap.get(downId)
      if (child) {
        return `#T-${child.task_no ?? "?"} ${child.title || ""}`.trim()
      }
      return `#T-${downId.slice(0, 4)}`
    })
  } else {
    downstreamTargets = ["终局闭环 · 产物反哺资产"]
  }

  // 4. 🛡 结果谁背书（核验）
  let endorsement = "自动化守卫评审"
  if (current.status === "waiting_acceptance") {
    endorsement = "等待人工商业决策拍板"
  } else if (current.status === "completed") {
    endorsement = "✓ 监察评审通过"
  } else if (current.status === "failed") {
    endorsement = "⛔ 质检异常 / 触发打回"
  } else if (current.acceptance && typeof current.acceptance === "object") {
    const acc = current.acceptance as { criteria?: string }
    if (acc.criteria) {
      endorsement = acc.criteria
    }
  }

  return {
    sourceRef,
    upstreamSummary,
    downstreamTargets,
    endorsement,
  }
}

export interface QueueHitlItem {
  request_id: string
  thread_id: string
  type: string
  description: string
  context: string | null
  options: string[]
  task_id?: string | null
  task_title?: string | null
  created_at?: string | null
}

/**
 * 转换单个 QueueTask 为 DutyTask
 */
export function adaptQueueTaskToDutyTask(
  task: QueueTask,
  allTasksMap: Map<string, QueueTask>,
  downstreamMap: Map<string, string[]>,
  hitlItem?: QueueHitlItem,
): DutyTask {
  const taskNo = task.task_no ?? 0
  const title =
    task.title ||
    (task as unknown as { task_data?: { title?: string } }).task_data?.title ||
    task.description?.slice(0, 32) ||
    `任务 #${taskNo}`

  // category 无值时保持空——UI 按缺省隐藏徽标，不再伪造"通用值守"假分类
  const category =
    task.category ||
    (task as unknown as { task_data?: { category?: string } }).task_data?.category ||
    ""

  const rawSourceRef = (task as unknown as { source_ref?: unknown }).source_ref
  const triggerSpec = (task as unknown as { trigger_spec?: string | null }).trigger_spec
  const source = mapSourceKind(task.source, rawSourceRef, triggerSpec)
  let status = mapStatus(task.status)
  const priority = (task.priority?.toLowerCase() as TaskPriority) || "medium"
  const riskLevel = ((task.risk_level || "T4").toUpperCase() as TaskRiskLevel) || "T4"
  const dependencies = task.dependencies || []

  // 四问一屏关系计算
  const provenance = buildFourQuestions(task, allTasksMap, downstreamMap)

  // 真实产物提取：若后端无真实产物则为 undefined，绝不捏造
  let artifact: DutyArtifact | undefined = undefined
  if (task.artifacts && task.artifacts.length > 0) {
    artifact = adaptQueueArtifactToDutyArtifact(task.artifacts[0])
  }

  // 商业拍板 / 验收数据：仅在真实 waiting_acceptance 且包含 signoff 数据时呈现
  let signoff: SignoffSpec | undefined = undefined
  if (status === "waiting_acceptance" && (task as unknown as { signoff?: SignoffSpec }).signoff) {
    signoff = (task as unknown as { signoff: SignoffSpec }).signoff
  }

  // HITL 安全与资金审批门禁
  let hitl: import("./types").HitlSpec | undefined = undefined
  let humanRequest: import("./types").HumanRequestSpec | undefined = undefined
  if (hitlItem) {
    if (status === "in_progress") {
      status = "confirm"
    }
    hitl = {
      pending: true,
      requestId: hitlItem.request_id,
      action: hitlItem.type,
      description: hitlItem.description,
    }
    humanRequest = {
      id: hitlItem.request_id,
      type: (hitlItem.type as any) || "approval",
      prompt: hitlItem.description,
      options:
        hitlItem.options && hitlItem.options.length > 0
          ? hitlItem.options
          : ["取消", "拒绝", "仅本次允许", "总是允许"],
      context: hitlItem.context || undefined,
      status: "waiting_human",
    }
  }

  // 执行步骤与时序：仅使用真实步骤，不伪造假进度
  const steps: import("./types").ExecutionStep[] = (task as unknown as { steps?: import("./types").ExecutionStep[] }).steps || []

  return {
    id: task.id,
    taskNo,
    title,
    description: task.description || undefined,
    category,
    status,
    priority,
    riskLevel,
    source,
    provenance,
    dependencies,
    stage: category,
    x: 0,
    y: 0,
    w: 320,
    h: 180,
    run: task.run
      ? {
          threadId: task.run.thread_id,
          llmCalls: task.run.llm_calls,
          inputTokens: task.run.input_tokens,
          outputTokens: task.run.output_tokens,
          toolErrors: task.run.tool_errors,
        }
      : undefined,
    steps,
    artifact,
    signoff,
    hitl,
    humanRequest,
    lastThreadId: task.last_thread_id,
    workflowId: task.workflow_id ?? null,
    workflowName: (task as { workflow_name?: string | null }).workflow_name ?? null,
    workflowRound:
      (
        task.provenance as { round?: number } | null | undefined
      )?.round ?? null,
    projectId: task.project_id,
    dueAt: task.due_at,
    createdAt: task.created_at,
    rawQueueTask: task,
  }
}

/**
 * 批量转换后端 QueueTask 列表为 DutyTask 列表
 * 同时构建全任务 Map 与下游反向索引表，并合并待审批 HITL 请求
 */
export function adaptQueueTasksToDutyTasks(
  tasks: QueueTask[],
  hitlItems?: QueueHitlItem[],
): DutyTask[] {
  const allTasksMap = new Map<string, QueueTask>()
  const downstreamMap = new Map<string, string[]>()

  // 构建 hitl 索引 map (以 task_id 或 thread_id 为索引)
  const hitlByTaskId = new Map<string, QueueHitlItem>()
  const hitlByThreadId = new Map<string, QueueHitlItem>()
  if (hitlItems) {
    for (const h of hitlItems) {
      if (h.task_id) hitlByTaskId.set(h.task_id, h)
      if (h.thread_id) hitlByThreadId.set(h.thread_id, h)
    }
  }

  for (const t of tasks) {
    allTasksMap.set(t.id, t)
    const deps = t.dependencies || []
    for (const depId of deps) {
      const existing = downstreamMap.get(depId) || []
      existing.push(t.id)
      downstreamMap.set(depId, existing)
    }
  }

  return tasks.map((t) => {
    const hitl =
      hitlByTaskId.get(t.id) ||
      (t.last_thread_id ? hitlByThreadId.get(t.last_thread_id) : undefined)
    return adaptQueueTaskToDutyTask(t, allTasksMap, downstreamMap, hitl)
  })
}
