import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { fireEvent, render, screen } from "@testing-library/react"
import { beforeEach, describe, expect, it, vi } from "vitest"
import { TasksQueueService } from "@/client"
import { WorkflowProposalCard } from "./WorkflowProposalCard"

vi.mock("@/client", () => ({
  TasksQueueService: {
    confirmWorkflow: vi.fn().mockResolvedValue({}),
    editWorkflow: vi.fn().mockResolvedValue({}),
  },
}))

describe("WorkflowProposalCard component", () => {
  let queryClient: QueryClient

  beforeEach(() => {
    queryClient = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    })
    vi.clearAllMocks()
  })

  const wrapper = ({ children }: { children: React.ReactNode }) => (
    <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
  )

  const sampleWorkflow = {
    id: "wf-123",
    project_id: 1,
    title: "每日竞品监控流水线",
    goal: "追踪市场变动并产出报告",
    status: "proposed",
    trigger_spec: "0 9 * * *",
    next_run_at: null,
    round_no: 1,
    stages: [
      { key: "fetch", title: "采集数据", deps: [] },
      { key: "analyze", title: "清洗分析", deps: ["fetch"] },
    ],
    created_at: "2026-09-27T00:00:00Z",
    updated_at: "2026-09-27T00:00:00Z",
  }

  it("renders proposed workflow details and stages", () => {
    render(
      <WorkflowProposalCard
        workflow={sampleWorkflow}
        onChanged={vi.fn()}
      />,
      { wrapper },
    )

    expect(screen.getByText("每日竞品监控流水线")).toBeInTheDocument()
    expect(screen.getByText("追踪市场变动并产出报告")).toBeInTheDocument()
    expect(screen.getByText("⏰ 0 9 * * *")).toBeInTheDocument()
    expect(screen.getByText("采集数据")).toBeInTheDocument()
    expect(screen.getByText("清洗分析")).toBeInTheDocument()
    expect(
      screen.getByRole("button", { name: /确认上膛/ }),
    ).toBeInTheDocument()
  })

  it("handles confirm workflow click", async () => {
    const onChanged = vi.fn()
    render(
      <WorkflowProposalCard
        workflow={sampleWorkflow}
        onChanged={onChanged}
      />,
      { wrapper },
    )

    const confirmBtn = screen.getByRole("button", { name: /确认上膛/ })
    fireEvent.click(confirmBtn)

    expect(TasksQueueService.confirmWorkflow).toHaveBeenCalledWith({
      workflowId: "wf-123",
    })
  })

  it("handles cancel workflow click", async () => {
    const onChanged = vi.fn()
    render(
      <WorkflowProposalCard
        workflow={sampleWorkflow}
        onChanged={onChanged}
      />,
      { wrapper },
    )

    const cancelBtn = screen.getByRole("button", { name: "取消" })
    fireEvent.click(cancelBtn)

    expect(TasksQueueService.editWorkflow).toHaveBeenCalledWith({
      workflowId: "wf-123",
      requestBody: { cancel: true },
    })
  })

  it("renders armed or running status banners", () => {
    render(
      <WorkflowProposalCard
        workflow={{ ...sampleWorkflow, status: "armed" }}
        onChanged={vi.fn()}
      />,
      { wrapper },
    )

    expect(screen.getByText("已上膛，等待触发周期")).toBeInTheDocument()
    expect(
      screen.queryByRole("button", { name: /确认上膛/ }),
    ).not.toBeInTheDocument()
  })
})
