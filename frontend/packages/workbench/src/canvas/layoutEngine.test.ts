import { describe, expect, it } from "vitest"
import type { DutyTask } from "../core/types"
import {
  CARD_HEIGHT,
  CARD_WIDTH,
  deriveDutyEdges,
  layoutDutyTasks,
  pruneTransitiveEdges,
} from "./layoutEngine"

describe("layoutEngine canvas topological layout", () => {
  const mockTask = (
    id: string,
    taskNo: number,
    deps: string[] = [],
    overrides: Partial<DutyTask> = {},
  ): DutyTask => ({
    id,
    taskNo,
    title: `Task ${taskNo}`,
    status: "pending",
    category: "research",
    priority: "medium",
    riskLevel: "T1",
    source: "manual",
    dependencies: deps,
    provenance: {
      sourceRef: "test",
      upstreamSummary: "",
      downstreamTargets: [],
      endorsement: "",
    },
    x: 0,
    y: 0,
    w: CARD_WIDTH,
    h: CARD_HEIGHT,
    ...overrides,
  })

  it("handles empty tasks list gracefully", () => {
    const res = layoutDutyTasks([])
    expect(res.tasks).toEqual([])
    expect(res.edges).toEqual([])
  })

  it("prunes transitive edges in DAG (A->B, B->C, A->C => eliminates A->C)", () => {
    const tasks: DutyTask[] = [
      mockTask("A", 1, []),
      mockTask("B", 2, ["A"]),
      mockTask("C", 3, ["B", "A"]), // A->C is transitive redundancy
    ]

    const reduced = pruneTransitiveEdges(tasks)
    expect(reduced).toEqual([
      { from: "A", to: "B" },
      { from: "B", to: "C" },
    ])

    const edges = deriveDutyEdges(tasks)
    expect(edges.length).toBe(2)
    expect(edges.find((e) => e.from === "A" && e.to === "C")).toBeUndefined()
  })

  it("assigns non-overlapping coordinates in horizontal mindmap layout", () => {
    const tasks: DutyTask[] = [
      mockTask("t1", 1, []),
      mockTask("t2", 2, ["t1"]),
      mockTask("t3", 3, ["t1"]),
    ]

    const result = layoutDutyTasks(tasks, undefined, "horizontal", "mindmap")
    expect(result.tasks.length).toBe(3)

    const t1 = result.tasks.find((t) => t.id === "t1")!
    const t2 = result.tasks.find((t) => t.id === "t2")!
    const t3 = result.tasks.find((t) => t.id === "t3")!

    // Downstream tasks should be to the right of root
    expect(t2.x).toBeGreaterThan(t1.x)
    expect(t3.x).toBeGreaterThan(t1.x)
    // Sibling tasks should not vertically overlap
    expect(Math.abs(t2.y - t3.y)).toBeGreaterThanOrEqual(CARD_HEIGHT)
  })

  it("supports pipeline strategy positioning sequentially", () => {
    const tasks: DutyTask[] = [
      mockTask("t1", 1, []),
      mockTask("t2", 2, ["t1"]),
      mockTask("t3", 3, ["t2"]),
    ]

    const result = layoutDutyTasks(tasks, undefined, "horizontal", "pipeline")
    expect(result.tasks.length).toBe(3)

    const [first, second, third] = result.tasks
    expect(second.x).toBeGreaterThan(first.x)
    expect(third.x).toBeGreaterThan(second.x)
  })

  it("handles circular dependency safely without infinite loop", () => {
    const tasks: DutyTask[] = [
      mockTask("cA", 1, ["cB"]),
      mockTask("cB", 2, ["cA"]),
    ]

    const result = layoutDutyTasks(tasks)
    expect(result.tasks.length).toBe(2)
  })
})
