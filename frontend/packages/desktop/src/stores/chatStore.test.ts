import { beforeEach, describe, expect, it, vi } from "vitest"
import { useChatStore } from "./chatStore"

describe("useChatStore state store", () => {
  beforeEach(() => {
    useChatStore.setState({
      threadId: null,
      projectId: null,
      messages: [],
      isSending: false,
      isTerminalMode: false,
      terminalHistoryBuffer: "",
      activeTasks: {},
      selectedModel: "default-model",
      pendingTaskDraft: null,
      pendingCreateTask: null,
    })
    vi.clearAllMocks()
  })

  it("sets terminal mode", () => {
    expect(useChatStore.getState().isTerminalMode).toBe(false)
    useChatStore.getState().setTerminalMode(true)
    expect(useChatStore.getState().isTerminalMode).toBe(true)
  })

  it("appends terminal output to buffer", () => {
    useChatStore.getState().appendTerminalOutput("Line 1\n")
    useChatStore.getState().appendTerminalOutput("Line 2\n")
    expect(useChatStore.getState().terminalHistoryBuffer).toBe(
      "Line 1\nLine 2\n",
    )
  })

  it("updates and removes active tasks in terminal mode", () => {
    const task = {
      task_id: "proc-1",
      task_type: "command",
      title: "npm run build",
      output: "",
      metadata: {},
      status: "running",
      created_at: new Date().toISOString(),
    }

    useChatStore.getState().updateActiveTask(task)
    expect(useChatStore.getState().activeTasks["proc-1"]).toEqual(task)

    useChatStore.getState().removeActiveTask("proc-1")
    expect(useChatStore.getState().activeTasks["proc-1"]).toBeUndefined()
  })

  it("updates selected model", () => {
    useChatStore.getState().setSelectedModel("gpt-4o")
    expect(useChatStore.getState().selectedModel).toBe("gpt-4o")
  })

  it("clears messages content", () => {
    useChatStore.setState({
      messages: [
        {
          id: "m-1",
          role: "user",
          content: "Hello",
          timestamp: new Date().toISOString(),
        } as any,
      ],
    })

    expect(useChatStore.getState().messages.length).toBe(1)
    useChatStore.getState().clearContent()
    expect(useChatStore.getState().messages.length).toBe(0)
  })

  it("sets pending task draft and creation data", () => {
    useChatStore.getState().setPendingTaskDraft("优化搜索：增加过滤项")
    expect(useChatStore.getState().pendingTaskDraft).toBe(
      "优化搜索：增加过滤项",
    )

    useChatStore.getState().setPendingCreateTask({
      taskId: "t-123",
      secret: "sec-456",
      callbackUrl: "http://localhost/callback",
    })
    expect(useChatStore.getState().pendingCreateTask?.taskId).toBe("t-123")
  })

  it("truncates messages to a specified index", () => {
    useChatStore.setState({
      messages: [
        { id: "1", role: "user", content: "1" } as any,
        { id: "2", role: "ai", content: "2" } as any,
        { id: "3", role: "user", content: "3" } as any,
      ],
    })

    useChatStore.getState()._truncateMessages(1)
    expect(useChatStore.getState().messages.length).toBe(1)
    expect(useChatStore.getState().messages.map((m) => m.id)).toEqual(["1"])
  })

  it("clears human request from last message", () => {
    useChatStore.setState({
      messages: [
        {
          id: "1",
          role: "ai",
          content: "Wait",
          humanRequest: { id: "req-1" } as any,
        } as any,
      ],
    })

    useChatStore.getState()._clearHumanRequest()
    expect(
      useChatStore.getState().messages[0].humanRequest,
    ).toBeUndefined()
  })
})
