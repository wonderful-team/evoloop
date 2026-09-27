import { act, fireEvent, render, screen } from "@testing-library/react"
import { describe, expect, it, vi } from "vitest"
import { TaskProposalCard } from "./TaskProposalCard"

describe("TaskProposalCard component", () => {
  it("renders standard proposal card with title, description, and metadata", () => {
    render(
      <TaskProposalCard
        id="prop-1"
        title="抓取 Twitter 趋势"
        description="自动抓取关键词趋势线索"
        priority="high"
        riskLevel="low"
        category="spider"
      />,
    )

    expect(screen.getByText("抓取 Twitter 趋势")).toBeInTheDocument()
    expect(screen.getByText("自动抓取关键词趋势线索")).toBeInTheDocument()
    expect(screen.getByText("high")).toBeInTheDocument()
    expect(screen.getByText(/spider/)).toBeInTheDocument()
  })

  it("handles confirm click in standard mode", async () => {
    const onConfirm = vi.fn().mockResolvedValue(undefined)
    render(
      <TaskProposalCard
        id="prop-2"
        title="确认测试提案"
        onConfirm={onConfirm}
      />,
    )

    const confirmBtn = screen.getByRole("button", { name: /确认，加入队列/ })
    await act(async () => {
      fireEvent.click(confirmBtn)
    })
    expect(onConfirm).toHaveBeenCalledTimes(1)
  })

  it("handles reject click directly when requireFeedbackOnReject is false", async () => {
    const onReject = vi.fn().mockResolvedValue(undefined)
    render(
      <TaskProposalCard
        id="prop-3"
        title="驳回测试提案"
        onReject={onReject}
        requireFeedbackOnReject={false}
      />,
    )

    const rejectBtn = screen.getByRole("button", { name: /取消/ })
    await act(async () => {
      fireEvent.click(rejectBtn)
    })
    expect(onReject).toHaveBeenCalledWith("")
  })

  it("requires feedback on reject when requireFeedbackOnReject is true", async () => {
    const onReject = vi.fn().mockResolvedValue(undefined)
    render(
      <TaskProposalCard
        id="prop-4"
        title="需反馈驳回提案"
        onReject={onReject}
        requireFeedbackOnReject={true}
      />,
    )

    const rejectTrigger = screen.getByRole("button", { name: /驳回/ })
    await act(async () => {
      fireEvent.click(rejectTrigger)
    })

    // Textarea appears
    const textarea = screen.getByPlaceholderText(/驳回原因（必填/i)
    expect(textarea).toBeInTheDocument()

    const confirmRejectBtn = screen.getByRole("button", { name: "确认驳回" })
    expect(confirmRejectBtn).toBeDisabled()

    await act(async () => {
      fireEvent.change(textarea, { target: { value: "数据源格式不符合预期" } })
    })
    expect(confirmRejectBtn).not.toBeDisabled()

    await act(async () => {
      fireEvent.click(confirmRejectBtn)
    })
    expect(onReject).toHaveBeenCalledWith("数据源格式不符合预期")
  })

  it("renders inline variant correctly", async () => {
    const onConfirm = vi.fn().mockResolvedValue(undefined)
    render(
      <TaskProposalCard
        variant="inline"
        id="prop-inline"
        title="内联任务提案"
        onConfirm={onConfirm}
      />,
    )

    expect(screen.getByText("产生提案")).toBeInTheDocument()
    expect(screen.getByText("内联任务提案")).toBeInTheDocument()
    expect(screen.getByText("待确认")).toBeInTheDocument()

    const confirmBtn = screen.getByRole("button", { name: /确认，加入队列/ })
    await act(async () => {
      fireEvent.click(confirmBtn)
    })
    expect(onConfirm).toHaveBeenCalled()
  })

  it("renders non-proposed terminal states with status banner and open duty action", () => {
    const onOpenDuty = vi.fn()
    render(
      <TaskProposalCard
        id="prop-done"
        title="已完成任务"
        status="completed"
        onOpenDuty={onOpenDuty}
      />,
    )

    expect(screen.getByText("任务已完成")).toBeInTheDocument()
    const openDutyBtn = screen.getByRole("button", { name: /打开值守/ })
    fireEvent.click(openDutyBtn)
    expect(onOpenDuty).toHaveBeenCalledTimes(1)
  })
})
