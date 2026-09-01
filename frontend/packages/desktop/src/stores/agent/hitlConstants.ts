// HITL 状态契约常量
// 与后端 messages / human_requests 的状态值对齐（单一来源，避免散落字符串）。
// 后端规范见 backend/app/core/hitl/constants.py。

export const HITL_STATUS = {
  waitingHuman: "waiting_human",
  humanInterrupt: "human_interrupt",
  interrupted: "interrupted",
  idle: "idle",
  stopped: "stopped",
  done: "done",
  failed: "failed",
  cancelled: "cancelled",
  completed: "completed",
} as const

// 原始状态 → 归一化 "interrupted" 的待处理集合
export const HITL_PENDING_STATUSES: string[] = [
  HITL_STATUS.waitingHuman,
  HITL_STATUS.humanInterrupt,
  HITL_STATUS.interrupted,
]

// 原始状态 → 归一化 "idle" 的结束集合
export const HITL_ENDED_STATUSES: string[] = [
  HITL_STATUS.done,
  HITL_STATUS.failed,
  HITL_STATUS.cancelled,
]

// 归一化后视为"空闲/可交互"的状态集合
export const AGENT_IDLE_STATUSES: string[] = [
  HITL_STATUS.idle,
  HITL_STATUS.stopped,
  HITL_STATUS.interrupted,
]