import {describe, expect, it, vi} from "vitest"

import {createCoalescedInvalidate, type DutySseActions, handleTaskQueueEvent, parseTaskQueueEvent,} from "./dutySse"

/** liveRun 残留回归（2026-09-23）：终态清除认 status 不认事件名 */
function mkActions() {
  const setLiveRun = vi.fn()
  const invalidate = vi.fn()
  const actions: DutySseActions = { setLiveRun, invalidate }
  return { setLiveRun, invalidate, actions }
}

describe("parseTaskQueueEvent", () => {
  it("合法 JSON → payload", () => {
    expect(
      parseTaskQueueEvent('{"event":"task_advanced","status":"completed"}'),
    ).toEqual({ event: "task_advanced", status: "completed" })
  })

  it("非法 JSON / 非对象 → null（不抛）", () => {
    expect(parseTaskQueueEvent("not-json")).toBeNull()
    expect(parseTaskQueueEvent('"plain-string"')).toBeNull()
    expect(parseTaskQueueEvent(undefined)).toBeNull()
  })
})

describe("handleTaskQueueEvent · liveRun 信号", () => {
  it("task_taken → 亮", () => {
    const { setLiveRun, actions } = mkActions()
    handleTaskQueueEvent(
      { event: "task_taken", title: "巡检", at: "2026-09-23T00:00:00Z" },
      actions,
    )
    expect(setLiveRun).toHaveBeenCalledWith(
      expect.objectContaining({ title: "巡检" }),
    )
  })

  it.each(["task_advanced", "task_accepted", "task_rejected", "task_updated"])(
    "%s + 终态 status → 灭（只认 task_updated 会漏掉前三者）",
    (event) => {
      const { setLiveRun, actions } = mkActions()
      handleTaskQueueEvent({ event, status: "completed" }, actions)
      expect(setLiveRun).toHaveBeenCalledWith(null)
    },
  )

  it.each(["completed", "failed", "cancelled"])(
    "终态 status=%s → 灭",
    (status) => {
      const { setLiveRun, actions } = mkActions()
      handleTaskQueueEvent({ event: "task_advanced", status }, actions)
      expect(setLiveRun).toHaveBeenCalledWith(null)
    },
  )

  it("非终态（in_progress/pending）→ liveRun 不动", () => {
    const { setLiveRun, actions } = mkActions()
    handleTaskQueueEvent({ event: "task_advanced", status: "pending" }, actions)
    expect(setLiveRun).not.toHaveBeenCalled()
  })
})

describe("handleTaskQueueEvent · invalidate 路由", () => {
  it("hitl_created/resolved → 额外失效 dutyHitl", () => {
    const { invalidate, actions } = mkActions()
    handleTaskQueueEvent({ event: "hitl_created" }, actions)
    expect(invalidate).toHaveBeenCalledWith("dutyHitl")
    expect(invalidate).toHaveBeenCalledWith(
      "dutyQueue",
      "dutyDashboard",
      "dutyPlan",
      "dutyExec",
    )

    handleTaskQueueEvent({ event: "hitl_resolved" }, actions)
    expect(invalidate).toHaveBeenCalledWith("dutyHitl")
  })

  it("普通任务事件 → 只失效队列/看板/计划/执行流四键", () => {
    const { invalidate, actions } = mkActions()
    handleTaskQueueEvent({ event: "task_advanced", status: "pending" }, actions)
    expect(invalidate).toHaveBeenCalledTimes(1)
    expect(invalidate).toHaveBeenCalledWith(
      "dutyQueue",
      "dutyDashboard",
      "dutyPlan",
      "dutyExec",
    )
  })
})

describe("createCoalescedInvalidate", () => {
  it("合并突发窗口内的多次调用为一次批量 invalidate", () => {
    vi.useFakeTimers()
    const calls: string[][] = []
    const coalesce = createCoalescedInvalidate((...keys) => calls.push(keys), 250)
    // 模拟执行期突发：6 条事件 × 4 query
    for (let i = 0; i < 6; i++) coalesce("dutyQueue", "dutyDashboard", "dutyPlan", "dutyExec")
    vi.advanceTimersByTime(249)
    expect(calls).toHaveLength(0) // 窗口内零 refetch
    vi.advanceTimersByTime(1)
    expect(calls).toHaveLength(1) // 尾沿一次批量
    expect(calls[0]).toEqual(["dutyQueue", "dutyDashboard", "dutyPlan", "dutyExec"])
    vi.useRealTimers()
  })

  it("后续窗口独立触发（不吞下一波事件）", () => {
    vi.useFakeTimers()
    const calls: string[][] = []
    const coalesce = createCoalescedInvalidate((...keys) => calls.push(keys), 250)
    coalesce("dutyQueue")
    vi.advanceTimersByTime(300)
    expect(calls).toHaveLength(1)
    coalesce("dutyQueue")
    vi.advanceTimersByTime(300)
    expect(calls).toHaveLength(2)
    vi.useRealTimers()
  })
})
