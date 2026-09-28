import { render, screen, fireEvent } from "@testing-library/react"
import { describe, it, expect, vi } from "vitest"
import { RunningTasksDock } from "./RunningTasksDock"
import { useChatStore } from "@/stores/chatStore"
import type { ActiveTaskInfo } from "@/stores/chat/types"

describe("RunningTasksDock", () => {
  it("renders null when activeTasks is empty", () => {
    useChatStore.setState({ activeTasks: {} })
    const { container } = render(<RunningTasksDock />)
    expect(container).toBeEmptyDOMElement()
  })

  it("renders running tasks with title and handles terminal click & stop click", () => {
    const cancelTaskSpy = vi.fn()
    useChatStore.setState({
      activeTasks: {
        "task-1": {
          task_id: "task-1",
          title: "pytest tests/test_core.py",
          status: "running",
        } as ActiveTaskInfo,
        "task-2": {
          task_id: "task-2",
          title: "npm run build --mode production",
          status: "pending",
        } as ActiveTaskInfo,
      },
      cancelTask: cancelTaskSpy,
    })

    render(<RunningTasksDock />)

    expect(screen.getByText("pytest tests/test_core.py")).toBeInTheDocument()
    expect(screen.getByText("npm run build --mode production")).toBeInTheDocument()

    // Click on the first task button to open terminal
    const taskBtn = screen.getByText("pytest tests/test_core.py").closest("button")
    expect(taskBtn).not.toBeNull()
    fireEvent.click(taskBtn!)
    expect(useChatStore.getState().isTerminalMode).toBe(true)

    // Stop button is visible for running task
    const stopBtns = screen.getAllByTitle("chat.runningTasks.stop")
    expect(stopBtns).toHaveLength(1) // only task-1 is running
    fireEvent.click(stopBtns[0])
    expect(cancelTaskSpy).toHaveBeenCalledWith("task-1")
  })
})
