import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { act, fireEvent, render, screen } from "@testing-library/react"
import { beforeEach, describe, expect, it, vi } from "vitest"
import { AgentService } from "@/client/sdk.gen"
import { DutyHitlInputCard } from "./DutyHitlInputCard"

vi.mock("@/client/sdk.gen", () => ({
  AgentService: {
    resumeChat: vi.fn().mockResolvedValue({}),
    stopChat: vi.fn().mockResolvedValue({}),
    cancelHitlRequest: vi.fn().mockResolvedValue({}),
  },
}))

describe("DutyHitlInputCard canvas component", () => {
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

  const sampleHitl = {
    request_id: "req-001",
    thread_id: "thread-hitl-001",
    type: "choice",
    description: "选择部署目标环境",
    options: ["staging", "production"],
    task_id: "task-001",
    task_title: "自动化部署",
    task_no: 7,
  }

  it("renders HITL prompt, task title, and options", () => {
    render(<DutyHitlInputCard hitl={sampleHitl} />, { wrapper })

    expect(screen.getByText("待决策审批")).toBeInTheDocument()
    expect(screen.getByText("#T-7 自动化部署")).toBeInTheDocument()
    expect(screen.getByText("选择部署目标环境")).toBeInTheDocument()
    expect(screen.getByText("staging")).toBeInTheDocument()
    expect(screen.getByText("production")).toBeInTheDocument()
  })

  it("submits selected option on confirm", async () => {
    const onResolved = vi.fn()
    render(
      <DutyHitlInputCard hitl={sampleHitl} onResolved={onResolved} />,
      { wrapper },
    )

    const confirmBtn = screen.getByRole("button", { name: /执行所选策略/i })
    await act(async () => {
      fireEvent.click(confirmBtn)
    })

    expect(AgentService.resumeChat).toHaveBeenCalledWith({
      requestBody: {
        thread_id: "thread-hitl-001",
        user_input: "staging",
        grant_mode: "once",
      },
    })
  })

  it("handles reject action", async () => {
    const onResolved = vi.fn()
    render(
      <DutyHitlInputCard hitl={sampleHitl} onResolved={onResolved} />,
      { wrapper },
    )

    const rejectBtn = screen.getByRole("button", { name: /驳回终止/i })
    await act(async () => {
      fireEvent.click(rejectBtn)
    })

    expect(AgentService.stopChat).toHaveBeenCalledWith({
      requestBody: {
        thread_id: "thread-hitl-001",
        message: "",
      },
    })
    expect(AgentService.cancelHitlRequest).toHaveBeenCalledWith({
      requestBody: {
        thread_id: "thread-hitl-001",
        reason: "值守操作员驳回",
      },
    })
  })
})
