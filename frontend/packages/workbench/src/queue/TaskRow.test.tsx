import "@testing-library/jest-dom/vitest"
import {render, screen} from "@testing-library/react"
import {QueryClient, QueryClientProvider} from "@tanstack/react-query"
import {describe, expect, it, vi} from "vitest"

import {TaskRow} from "./TaskRow"
import type {QueueTask} from "@/lib/tasksQueueApi"

/**
 * TaskRow 状态呈现契约（2026-09-23 收敛）：
 * - cancelled → "已取消" 标签（此前静默落空态）
 * - 评审中（review_pending）→ "评审中"（非"待人工验收"）
 * - 失败 → "失败"；仲裁升级 → "转人工仲裁·去处理"
 * - 依赖提示行
 */

vi.mock("@tanstack/react-router", () => ({
  useNavigate: () => vi.fn(),
}))

function mkTask(overrides: Partial<QueueTask> = {}): QueueTask {
  return {
    id: "t-1",
    task_no: 1,
    title: "售后巡检",
    description: "",
    type: "once",
    status: "pending",
    category: "refunds",
    priority: "medium",
    risk_level: "T4",
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

function renderRow(task: QueueTask) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={qc}>
      <TaskRow task={task} selected={false} onSelect={() => {}} />
    </QueryClientProvider>,
  )
}

describe("TaskRow 状态呈现", () => {
  it("cancelled → 已取消", () => {
    renderRow(mkTask({ status: "cancelled" }))
    expect(screen.getByText("已取消")).toBeInTheDocument()
  })

  it("评审中（review_pending）→ 评审中而非待人工验收", () => {
    renderRow(
      mkTask({ status: "waiting_acceptance", review_pending: true }),
    )
    expect(screen.getByText("评审中")).toBeInTheDocument()
    expect(screen.queryByText("待人工验收")).not.toBeInTheDocument()
  })

  it("waiting_acceptance（无 review_pending）→ 待人工验收", () => {
    renderRow(mkTask({ status: "waiting_acceptance" }))
    expect(screen.getByText("待人工验收")).toBeInTheDocument()
  })

  it("failed → 失败", () => {
    renderRow(mkTask({ status: "failed" }))
    expect(screen.getByText("失败")).toBeInTheDocument()
  })

  it("escalated → 转人工仲裁入口", () => {
    renderRow(mkTask({ status: "failed", escalated: true }))
    expect(screen.getByText(/转人工仲裁/)).toBeInTheDocument()
  })

  it("依赖任务 → 显示依赖提示行", () => {
    renderRow(mkTask({ dependencies: ["a", "b"] }))
    expect(screen.getByText(/依赖 2 项/)).toBeInTheDocument()
  })
})
