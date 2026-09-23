/**
 * 值守 SSE 事件处理（纯函数，便于回归测试）。
 *
 * 设计原则（§9.4）：事件是加速器，状态以服务端为准——本函数只做两类事：
 * 1) liveRun 状态条的即时信号（task_taken 亮 / 任意终态灭）
 * 2) 精准 invalidate（HITL 事件 → 审批计数；其余事件 → 队列/看板/计划/执行流）
 */

export interface TaskQueueEventPayload {
  event?: string
  title?: string | null
  status?: string
  at?: string
  tokens?: number
  thread_id?: string
}

export interface DutySseActions {
  setLiveRun: (v: { title: string; at: string } | null) => void
  /** 传 query key 首段（如 "dutyHitl"）；实现方负责 invalidateQueries */
  invalidate: (...keys: string[]) => void
}

const TERMINAL_STATUSES = ["completed", "failed", "cancelled"]
const HITL_EVENTS = new Set(["hitl_created", "hitl_resolved"])

export function parseTaskQueueEvent(data: unknown): TaskQueueEventPayload | null {
  try {
    const parsed = JSON.parse(typeof data === "string" ? data : String(data ?? ""))
    return typeof parsed === "object" && parsed !== null
      ? (parsed as TaskQueueEventPayload)
      : null
  } catch {
    return null
  }
}

export function handleTaskQueueEvent(
  payload: TaskQueueEventPayload,
  actions: DutySseActions,
): void {
  if (payload.event === "task_taken") {
    actions.setLiveRun({
      title: payload.title ?? "",
      at: payload.at ?? new Date().toISOString(),
    })
  } else if (
    // 终态清除不看事件名：正常推进发布 task_advanced（带 effective
    // status），验收发布 task_accepted/rejected，编辑发布 task_updated——
    // 只认 task_updated 会漏掉前两者，"正在执行"状态条就永久残留
    // （串行派发下当前 run 唯一，无需匹配 id）
    TERMINAL_STATUSES.includes(payload.status ?? "")
  ) {
    actions.setLiveRun(null)
  }
  if (payload.event && HITL_EVENTS.has(payload.event)) {
    actions.invalidate("dutyHitl")
  }
  actions.invalidate("dutyQueue", "dutyDashboard", "dutyPlan", "dutyExec")
}
