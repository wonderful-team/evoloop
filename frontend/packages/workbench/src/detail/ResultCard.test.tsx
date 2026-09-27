import "@testing-library/jest-dom/vitest"
import {render, screen} from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import {QueryClient, QueryClientProvider} from "@tanstack/react-query"
import {afterEach, beforeEach, describe, expect, it, vi} from "vitest"

import {ResultCard} from "./ResultCard"
import {type QueueTask, TasksQueueApi} from "@/lib/tasksQueueApi"

/**
 * ResultCard 终态/验收操作契约（2026-09-23 收敛）：
 * - waiting_acceptance → 人工验收按钮开放
 * - review_pending → 评审中只读横幅，验收/驳回按钮必须隐藏（防打断 reviewer）
 * - failed → "重新执行"入口（此前无入口，用户只能重建任务）
 * - accept 必带 result（后端契约）由后端守卫，前端按钮照常放行
 */

function mkTask(overrides: Partial<QueueTask> = {}): QueueTask {
  return {
    id: "t-1",
    task_no: 1,
    title: "任务一",
    description: "",
    type: "once",
    status: "waiting_acceptance",
    category: "orders",
    priority: "medium",
    risk_level: "T2",
    source: "agent",
    provenance: null,
    self_check: null,
    acceptance: null,
    due_at: null,
    last_thread_id: null,
    dependencies: [],
    origin_thread_id: "conv-1",
    ...overrides,
  } as QueueTask
}

function renderCard(task: QueueTask, props?: { onChanged?: () => void; onVerdictDone?: (x: string) => void }) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={qc}>
      <ResultCard
        task={task}
        finalText="已完成全部巡检"
        onChanged={props?.onChanged ?? (() => {})}
        onVerdictDone={props?.onVerdictDone}
      />
    </QueryClientProvider>,
  )
}

beforeEach(() => {
  vi.spyOn(TasksQueueApi, "accept").mockResolvedValue({ success: true, status: "completed" })
  vi.spyOn(TasksQueueApi, "rerun").mockResolvedValue({ success: true, status: "pending" })
  vi.spyOn(TasksQueueApi, "reject").mockResolvedValue({ success: true, status: "pending" })
})

afterEach(() => {
  vi.restoreAllMocks()
})

describe("ResultCard · 人工验收（waiting_acceptance，无 review_pending）", () => {
  it("显示验收/驳回按钮；点击验收调 accept API", async () => {
    const onChanged = vi.fn()
    const onVerdictDone = vi.fn()
    renderCard(mkTask(), { onChanged, onVerdictDone })

    const btn = screen.getByText(/商业验收通过/)
    await userEvent.click(btn)
    expect(TasksQueueApi.accept).toHaveBeenCalledWith("t-1")
    expect(onChanged).toHaveBeenCalled()
    expect(onVerdictDone).toHaveBeenCalledWith("done")
  })

  it("驳回必填反馈：无反馈时确认按钮不可用", async () => {
    renderCard(mkTask())
    await userEvent.click(screen.getByText(/驳回重做/))
    const confirm = screen.getByRole("button", { name: /确认驳回/ })
    expect(confirm).toBeDisabled()
  })
})

describe("ResultCard · 评审中（waiting_acceptance + review_pending）", () => {
  it("只读横幅：验收/驳回按钮不得出现（防打断 reviewer）", () => {
    renderCard(mkTask({ review_pending: true }))
    expect(screen.getByText(/评审 Agent 正在核验/)).toBeInTheDocument()
    expect(screen.queryByText(/商业验收通过/)).not.toBeInTheDocument()
    expect(screen.queryByText(/驳回重做/)).not.toBeInTheDocument()
  })
})

describe("ResultCard · 失败重跑", () => {
  it("failed 显示失败原因 + 重新执行；点击调 rerun API", async () => {
    const onVerdictDone = vi.fn()
    renderCard(mkTask({ status: "failed", last_error: "MySQL server has gone away" }), {
      onVerdictDone,
    })
    expect(screen.getByText(/MySQL server has gone away/)).toBeInTheDocument()
    await userEvent.click(screen.getByText(/重新执行/))
    expect(TasksQueueApi.rerun).toHaveBeenCalledWith("t-1")
    expect(onVerdictDone).toHaveBeenCalledWith("active")
  })

  it("两轮评审仲裁升级（escalated）→ 显示转人工横幅，不显示重跑按钮", () => {
    renderCard(mkTask({ status: "failed", escalated: true }))
    expect(screen.getByText(/转人工仲裁/)).toBeInTheDocument()
    expect(screen.queryByText(/重新执行/)).not.toBeInTheDocument()
  })
})
