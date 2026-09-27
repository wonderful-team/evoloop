import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { render, screen } from "@testing-library/react"
import { beforeEach, describe, expect, it, vi } from "vitest"
import { ConversationsService } from "@/client"
import { ReviewProgressCard } from "./ReviewProgressCard"

vi.mock("@/client", () => ({
  ConversationsService: {
    getConversationMessages: vi.fn(),
  },
  AgentService: {
    resumeChat: vi.fn().mockResolvedValue({}),
  },
  OpenAPI: {
    BASE: "http://localhost:8000",
    TOKEN: "mock-token",
  },
}))

describe("ReviewProgressCard component", () => {
  let queryClient: QueryClient

  beforeEach(() => {
    queryClient = new QueryClient({
      defaultOptions: {
        queries: { retry: false },
      },
    })
    vi.clearAllMocks()
  })

  const wrapper = ({ children }: { children: React.ReactNode }) => (
    <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
  )

  it("renders review in progress banner and default inspecting prompt", () => {
    vi.mocked(ConversationsService.getConversationMessages).mockResolvedValue({
      data: [],
    } as any)

    render(
      <ReviewProgressCard
        task={{
          id: "task-rev-1",
          task_no: 1,
          title: "测试任务",
          status: "waiting_acceptance",
          origin_thread_id: "thread-origin-123",
        } as any}
        hitlItems={[]}
        onChanged={vi.fn()}
      />,
      { wrapper },
    )

    expect(screen.getByText("监察评审进行中")).toBeInTheDocument()
    expect(screen.getByText("thread-origin-123")).toBeInTheDocument()
    expect(
      screen.getByText(/评审者正在核验（对照最初意图逐条核对/i),
    ).toBeInTheDocument()
  })

  it("renders pending HITL approval items when present", async () => {
    vi.mocked(ConversationsService.getConversationMessages).mockResolvedValue({
      data: [],
    } as any)

    const hitlItems = [
      {
        request_id: "hitl-req-1",
        type: "approval",
        description: "是否允许删除过期缓存？",
        thread_id: "thread-origin-123",
      },
    ]

    const onChanged = vi.fn()

    render(
      <ReviewProgressCard
        task={{
          id: "task-rev-2",
          task_no: 2,
          title: "数据清理",
          status: "waiting_acceptance",
          origin_thread_id: "thread-origin-123",
        } as any}
        hitlItems={hitlItems}
        onChanged={onChanged}
      />,
      { wrapper },
    )

    expect(screen.getByText("是否允许删除过期缓存？")).toBeInTheDocument()
  })
})
