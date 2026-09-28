/**
 * 值守 SSE 事件处理（纯函数，便于回归测试）。
 *
 * 设计原则（§9.4）：事件是加速器，状态以服务端为准——本函数只做两类事：
 * 1) liveRun 状态条的即时信号（task_taken 亮 / 任意终态灭）
 * 2) 精准 invalidate（HITL 事件 → 审批计数；其余事件 → 队列/看板/计划/执行流）
 */

export interface TaskQueueEventPayload {
  event?: string
  task_id?: string
  title?: string | null
  status?: string
  at?: string
  tokens?: number
  thread_id?: string
  /** queue_drained 战报计数（本轮值守完成汇总） */
  completed?: number
  failed?: number
  waiting?: number
  pending?: number
}

export interface DutySseActions {
  setLiveRun: (v: { title: string; at: string } | null) => void
  /** 传 query key 首段（如 "dutyHitl"）；实现方负责 invalidateQueries */
  invalidate: (...keys: string[]) => void
}

const TERMINAL_STATUSES = ["completed", "failed", "cancelled"]
const HITL_EVENTS = new Set(["hitl_created", "hitl_resolved"])

export function parseTaskQueueEvent(
  data: unknown,
): TaskQueueEventPayload | null {
  try {
    const parsed = JSON.parse(
      typeof data === "string" ? data : String(data ?? ""),
    )
    return typeof parsed === "object" && parsed !== null
      ? (parsed as TaskQueueEventPayload)
      : null
  } catch {
    return null
  }
}

/**
 * 事件突发合并器：任务执行期事件连发（taken/advanced/终态…每条 4 个
 * query），逐条 invalidate 会形成 refetch+重渲染风暴，主线程被压死后
 * 后续 SSE 回调饿死（实测负载高时事件计数掉 0）。改为 250ms 尾沿合并：
 * 突发窗口内 N 条事件只触发一次批量 invalidate，配合 react-query 的
 * inflight 去重，风暴消失。窗口只是合并调度，不改变状态收敛语义
 * （事件是加速器，最坏损失 250ms 实时性）。
 */
export function createCoalescedInvalidate(
  invalidate: (...keys: string[]) => void,
  windowMs = 250,
): (...keys: string[]) => void {
  const pending = new Set<string>()
  let timer: ReturnType<typeof setTimeout> | null = null
  return (...keys: string[]) => {
    for (const key of keys) pending.add(key)
    if (timer) return
    timer = setTimeout(() => {
      timer = null
      const batch = Array.from(pending)
      pending.clear()
      if (batch.length) invalidate(...batch)
    }, windowMs)
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
  if (
    (payload.event && payload.event.startsWith("workflow_")) ||
    (payload as { type?: string }).type === "workflow_updated"
  ) {
    actions.invalidate("dutyWorkflows")
  }
  actions.invalidate("dutyQueue", "dutyDashboard", "dutyPlan", "dutyExec")
}
