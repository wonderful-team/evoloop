import {describe, expect, it} from "vitest"

import {adaptQueueArtifactToDutyArtifact, adaptQueueTasksToDutyTasks,} from "./taskAdapter"
import type {QueueTask} from "@/lib/tasksQueueApi"

/** QueueTask 最小合法构造器（缺省字段按后端 /queue 返回形状） */
function mkTask(overrides: Partial<QueueTask> = {}): QueueTask {
  return {
    id: "t-1",
    task_no: 1,
    title: "任务一",
    description: "做点事",
    type: "once",
    status: "pending",
    category: "orders",
    priority: "medium",
    risk_level: "T3",
    source: "user",
    provenance: null,
    self_check: null,
    acceptance: null,
    due_at: null,
    last_thread_id: null,
    dependencies: [],
    ...overrides,
  } as QueueTask
}

describe("adaptQueueTasksToDutyTasks · 状态映射", () => {
  it("后端八个状态一一映射，未知状态回落 pending", () => {
    const statuses = [
      "proposed",
      "pending",
      "in_progress",
      "waiting_acceptance",
      "completed",
      "failed",
      "cancelled",
    ] as const
    const tasks = statuses.map((status, i) =>
      mkTask({ id: `t-${i}`, status }),
    )
    const mapped = adaptQueueTasksToDutyTasks(tasks)
    for (const t of mapped) {
      expect(t.status).toBe(t.id === "t-1" ? "pending" : t.status)
    }
    expect(mapped.map((t) => t.status)).toEqual([
      "proposed",
      "pending",
      "in_progress",
      "waiting_acceptance",
      "completed",
      "failed",
      "cancelled",
    ])
    // 未知/合成状态不得凭空产生
    const weird = adaptQueueTasksToDutyTasks([mkTask({ status: "weird" })])
    expect(weird[0].status).toBe("pending")
  })

  it("HITL 挂起：in_progress + 待审批 → confirm（资金/授权门禁）", () => {
    const mapped = adaptQueueTasksToDutyTasks(
      [mkTask({ id: "t-1", status: "in_progress", last_thread_id: "wakeup_1_x" })],
      [
        {
          request_id: "req-1",
          thread_id: "wakeup_1_x",
          type: "authorization",
          description: "放行该操作",
          context: null,
          options: [],
          created_at: null,
          task_id: "t-1",
          task_title: "任务一",
        },
      ],
    )
    expect(mapped[0].status).toBe("confirm")
    expect(mapped[0].hitl?.pending).toBe(true)
    expect(mapped[0].hitl?.requestId).toBe("req-1")
  })

  it("评审中：waiting_acceptance + review_pending 保留原状态", () => {
    const mapped = adaptQueueTasksToDutyTasks([
      mkTask({ status: "waiting_acceptance", review_pending: true }),
    ])
    expect(mapped[0].status).toBe("waiting_acceptance")
  })
})

describe("adaptQueueTasksToDutyTasks · 来源徽标映射（真实数据驱动）", () => {
  it("user 无血统 → manual（不再误标依赖派生）", () => {
    const mapped = adaptQueueTasksToDutyTasks([mkTask({ source: "user" })])
    expect(mapped[0].source).toBe("manual")
  })

  it("recurring（trigger_spec）→ cron，无论谁建的（T-14 场景回归）", () => {
    const mapped = adaptQueueTasksToDutyTasks([
      mkTask({ source: "user", trigger_spec: "0 */4 * * *" }),
    ])
    expect(mapped[0].source).toBe("cron")
  })

  it("agent → agent_proposal", () => {
    const mapped = adaptQueueTasksToDutyTasks([mkTask({ source: "agent" })])
    expect(mapped[0].source).toBe("agent_proposal")
  })

  it("source_ref.kind=message → chat（对话产生）", () => {
    const mapped = adaptQueueTasksToDutyTasks([
      mkTask({ source: "user", source_ref: { kind: "message", ref: "conv-1" } } as Partial<QueueTask>),
    ])
    expect(mapped[0].source).toBe("chat")
  })

  it("external / kind=event → event（外部事件）", () => {
    const a = adaptQueueTasksToDutyTasks([mkTask({ source: "external" })])
    const b = adaptQueueTasksToDutyTasks([
      mkTask({ source: "external", source_ref: { kind: "event", ref: "e-1" } } as Partial<QueueTask>),
    ])
    expect(a[0].source).toBe("event")
    expect(b[0].source).toBe("event")
  })

  it("kind=chain → chain（真正的依赖派生）", () => {
    const mapped = adaptQueueTasksToDutyTasks([
      mkTask({ source: "user", source_ref: { kind: "chain", ref: "t-1" } } as Partial<QueueTask>),
    ])
    expect(mapped[0].source).toBe("chain")
  })

  it("agent 身份优先于 chain（链上派生的提案仍走确认流，不得掉出 relatedProposals）", () => {
    const mapped = adaptQueueTasksToDutyTasks([
      mkTask({ source: "agent", source_ref: { kind: "chain", ref: "t-1" } } as Partial<QueueTask>),
    ])
    expect(mapped[0].source).toBe("agent_proposal")
  })

  it("category 缺省不再伪造“通用值守”", () => {
    const mapped = adaptQueueTasksToDutyTasks([mkTask({ category: null })])
    expect(mapped[0].category).toBeFalsy()
  })
})

describe("adaptQueueTasksToDutyTasks · DAG 四问", () => {
  it("依赖链：上游产出喂下游，下游因上游而生", () => {
    const a = mkTask({ id: "a", task_no: 1, title: "上游" })
    const b = mkTask({ id: "b", task_no: 2, title: "下游", dependencies: ["a"] })
    const mapped = adaptQueueTasksToDutyTasks([a, b])
    const upstream = mapped.find((t) => t.id === "a")!
    const downstream = mapped.find((t) => t.id === "b")!
    expect(downstream.dependencies).toEqual(["a"])
    // 四问：a 的下游反查包含 b（以下游短编号 #T-2 呈现）
    expect(upstream.provenance.downstreamTargets.join(" ")).toContain("#T-2")
  })

  it("孤儿依赖（上游不存在）不崩溃，依赖保留原样", () => {
    const mapped = adaptQueueTasksToDutyTasks([
      mkTask({ id: "b", dependencies: ["ghost"] }),
    ])
    expect(mapped[0].dependencies).toEqual(["ghost"])
  })
})

describe("adaptQueueArtifactToDutyArtifact · 产物类型推断", () => {
  it("type 关键词映射（matrix/gallery/funnel/copy/json/choice）", () => {
    const cases: Array<[string, string]> = [
      ["pricing_matrix", "matrix"],
      ["image_gallery", "gallery"],
      ["funnel_report", "funnel"],
      ["copy_text", "copy"],
      ["json_data", "json"],
      ["multi_choice", "choice"],
    ]
    for (const [raw, expected] of cases) {
      const art = adaptQueueArtifactToDutyArtifact({
        id: "a1",
        workflow_id: "wf",
        task_id: "t-1",
        stage: "stage1",
        type: raw,
        status: "generated",
        version: 1,
        summary: "s",
        data: null,
        created_at: "",
      })
      expect(art.type).toBe(expected)
    }
  })
})
