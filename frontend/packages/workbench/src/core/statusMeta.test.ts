import { describe, expect, it } from "vitest"
import { isTerminalStatus, statusMeta } from "./statusMeta"

describe("statusMeta core service", () => {
  it("provides correct metadata for all known task statuses", () => {
    expect(statusMeta("pending").label).toBe("待执行")
    expect(statusMeta("pending").terminal).toBe(false)
    expect(statusMeta("pending").cardCls).toBe("lock")

    expect(statusMeta("in_progress").label).toBe("执行中")
    expect(statusMeta("in_progress").terminal).toBe(false)
    expect(statusMeta("in_progress").glyph).toBe("⟳")

    expect(statusMeta("proposed").label).toBe("提案")
    expect(statusMeta("proposed").glyph).toBe("💡")

    expect(statusMeta("waiting_acceptance").label).toBe("待验收")
    expect(statusMeta("waiting_acceptance").terminal).toBe(false)

    expect(statusMeta("confirm").label).toBe("待安全授权")
    expect(statusMeta("confirm").dotCls).toContain("amber")

    expect(statusMeta("completed").label).toBe("已完成")
    expect(statusMeta("completed").terminal).toBe(true)
    expect(statusMeta("completed").glyph).toBe("✓")

    expect(statusMeta("failed").label).toBe("失败")
    expect(statusMeta("failed").terminal).toBe(true)
    expect(statusMeta("failed").glyph).toBe("⛔")

    expect(statusMeta("blocked").label).toBe("断链阻塞")
    expect(statusMeta("blocked").terminal).toBe(false)

    expect(statusMeta("cancelled").label).toBe("已取消")
    expect(statusMeta("cancelled").terminal).toBe(true)
  })

  it("fail-opens to pending metadata for unknown status strings", () => {
    const unknown = statusMeta("some_future_status")
    expect(unknown.label).toBe("待执行")
    expect(unknown.terminal).toBe(false)
    expect(unknown.cardCls).toBe("lock")
  })

  it("correctly identifies terminal statuses", () => {
    expect(isTerminalStatus("completed")).toBe(true)
    expect(isTerminalStatus("failed")).toBe(true)
    expect(isTerminalStatus("cancelled")).toBe(true)

    expect(isTerminalStatus("pending")).toBe(false)
    expect(isTerminalStatus("in_progress")).toBe(false)
    expect(isTerminalStatus("proposed")).toBe(false)
    expect(isTerminalStatus("waiting_acceptance")).toBe(false)
    expect(isTerminalStatus("confirm")).toBe(false)
    expect(isTerminalStatus("blocked")).toBe(false)
    expect(isTerminalStatus("unknown_status")).toBe(false)
  })
})
