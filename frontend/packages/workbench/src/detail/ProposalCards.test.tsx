import {render, screen} from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import {QueryClient, QueryClientProvider} from "@tanstack/react-query"
import {afterEach, beforeEach, describe, expect, it, vi} from "vitest"

import {ProposalCard} from "./ProposalCards"
import {type QueueTask, TasksQueueApi} from "@/lib/tasksQueueApi"

/**
 * 提案卡操作口径（2026-09-23 收敛回归）：
 * - 确认 → POST /confirm
 * - 驳回 → PUT cancel 语义（rejectProposed），绝不调 acceptance reject
 *   （acceptance reject 只接受 waiting_acceptance，对 proposed 必 409）
 */

vi.mock("@evoloop/shared", () => ({
  TaskProposalCard: ({
    onConfirm,
    onReject,
  }: {
    onConfirm: () => Promise<void>
    onReject: (feedback?: string) => Promise<void>
  }) => (
    <div>
      <button type="button" onClick={() => void onConfirm()}>
        确认提案
      </button>
      <button type="button" onClick={() => void onReject("方案不可行")}>
        驳回提案
      </button>
      <button type="button" onClick={() => void onReject(undefined)}>
        驳回无反馈
      </button>
    </div>
  ),
}))

function mkTask(overrides: Partial<QueueTask> = {}): QueueTask {
  return {
    id: "t-9",
    task_no: 9,
    title: "补货提案",
    description: "库存告急",
    type: "once",
    status: "proposed",
    category: "stock",
    priority: "high",
    risk_level: "T1",
    source: "agent",
    provenance: null,
    self_check: null,
    acceptance: null,
    due_at: null,
    last_thread_id: null,
    dependencies: [],
    ...overrides,
  } as QueueTask
}

function renderCard(task: QueueTask) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={qc}>
      <ProposalCard task={task} sourceTask={null} onChanged={() => {}} onConfirmed={() => {}} />
    </QueryClientProvider>,
  )
}

beforeEach(() => {
  vi.spyOn(TasksQueueApi, "confirm").mockResolvedValue({ success: true, status: "pending" })
  vi.spyOn(TasksQueueApi, "rejectProposed").mockResolvedValue({ success: true, status: "cancelled" })
  vi.spyOn(TasksQueueApi, "reject").mockResolvedValue({ success: true, status: "pending" })
})

afterEach(() => {
  vi.restoreAllMocks()
})

describe("ProposalCard 操作口径", () => {
  it("确认 → POST /confirm", async () => {
    renderCard(mkTask())
    await userEvent.click(screen.getByText("确认提案"))
    expect(TasksQueueApi.confirm).toHaveBeenCalledWith("t-9")
    expect(TasksQueueApi.rejectProposed).not.toHaveBeenCalled()
  })

  it("驳回（带反馈）→ PUT cancel，不调 reject", async () => {
    renderCard(mkTask())
    await userEvent.click(screen.getByText("驳回提案"))
    expect(TasksQueueApi.rejectProposed).toHaveBeenCalledWith("t-9", "方案不可行")
    expect(TasksQueueApi.reject).not.toHaveBeenCalled()
  })

  it("驳回无反馈 → 不发任何请求（requireFeedbackOnReject 语义）", async () => {
    renderCard(mkTask())
    await userEvent.click(screen.getByText("驳回无反馈"))
    expect(TasksQueueApi.rejectProposed).not.toHaveBeenCalled()
    expect(TasksQueueApi.reject).not.toHaveBeenCalled()
    expect(TasksQueueApi.confirm).not.toHaveBeenCalled()
  })
})
