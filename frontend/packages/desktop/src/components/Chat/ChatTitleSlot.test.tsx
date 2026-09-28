import { render, screen, fireEvent } from "@testing-library/react"
import { describe, it, expect, vi, beforeEach } from "vitest"
import { ChatTitleBreadcrumb, ChatTitleActions } from "./ChatTitleSlot"
import { useProjectStore } from "@/stores/projectStore"
import { useChatStore } from "@/stores/chatStore"
import { useAgentStore } from "@/stores/agentStore"
import { useUIStore } from "@/stores/uiStore"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"

vi.mock("@/client", () => ({
  PlanningService: {
    getPlan: vi.fn().mockResolvedValue({
      plan: {
        title: "重构登录逻辑",
        steps: [
          { description: "编写单元测试", status: "in_progress" },
        ],
      },
    }),
  },
}))

describe("ChatTitleSlot", () => {
  let queryClient: QueryClient

  beforeEach(() => {
    queryClient = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    })
  })

  describe("ChatTitleBreadcrumb", () => {
    it("renders project name and fallback ready status when no plan or goal", () => {
      useProjectStore.setState({ currentProject: { name: "Evoloop App" } as any })
      useChatStore.setState({ threadId: null, sessionGoal: null })
      useAgentStore.setState({ status: "idle", agentState: null })

      render(
        <QueryClientProvider client={queryClient}>
          <ChatTitleBreadcrumb />
        </QueryClientProvider>,
      )

      expect(screen.getByText("Evoloop App")).toBeInTheDocument()
      expect(screen.getByText("chat.status.ready")).toBeInTheDocument()
    })

    it("renders sessionGoal and running step when agent is running", () => {
      useProjectStore.setState({ currentProject: { name: "Evoloop App" } as any })
      useChatStore.setState({ threadId: "th-1", sessionGoal: "修复编译错误" })
      useAgentStore.setState({ status: "running", agentState: { task_name: "正在运行 Vite 打包" } as any })

      render(
        <QueryClientProvider client={queryClient}>
          <ChatTitleBreadcrumb />
        </QueryClientProvider>,
      )

      expect(screen.getByText("修复编译错误")).toBeInTheDocument()
      expect(screen.getByText("正在运行 Vite 打包")).toBeInTheDocument()
    })
  })

  describe("ChatTitleActions", () => {
    it("toggles chat list and context panel state in uiStore", () => {
      useUIStore.setState({
        isCompactWindow: false,
        showChatList: false,
        showContextPanel: false,
        miniMode: false,
      })

      render(<ChatTitleActions />)

      const toggleChatBtn = screen.getByTitle("common.openChatList")
      fireEvent.click(toggleChatBtn)
      expect(useUIStore.getState().showChatList).toBe(true)

      const toggleContextBtn = screen.getByTitle("common.openContextPanel")
      fireEvent.click(toggleContextBtn)
      expect(useUIStore.getState().showContextPanel).toBe(true)
    })

    it("toggles miniMode state", () => {
      useUIStore.setState({ miniMode: false })
      render(<ChatTitleActions />)

      const miniBtn = screen.getByTitle("common.miniMode")
      fireEvent.click(miniBtn)
      expect(useUIStore.getState().miniMode).toBe(true)
    })
  })
})
