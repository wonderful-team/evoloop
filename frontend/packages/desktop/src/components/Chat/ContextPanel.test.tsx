import { render, screen, fireEvent } from "@testing-library/react"
import { describe, it, expect, vi } from "vitest"
import { ContextPanel } from "./ContextPanel"
import { useAgentStore } from "@/stores/agentStore"

vi.mock("./context/ActivityTab", () => ({
  ActivityTab: ({ activeThreadId }: any) => (
    <div data-testid="activity-tab">Activity Tab for {activeThreadId}</div>
  ),
}))

vi.mock("./context/ContextGroupTab", () => ({
  ContextGroupTab: ({ projectId }: any) => (
    <div data-testid="context-tab">Context Tab for {projectId}</div>
  ),
}))

describe("ContextPanel", () => {
  it("renders header, close button, and activity tab by default", () => {
    const onClose = vi.fn()
    useAgentStore.setState({ status: "idle" })

    render(
      <ContextPanel
        projectId={42}
        activeThreadId="thread-99"
        onClose={onClose}
      />,
    )

    expect(screen.getByText("chat.context.title")).toBeInTheDocument()
    expect(screen.getByTestId("activity-tab")).toBeInTheDocument()

    // Close button
    const closeBtn = screen.getAllByRole("button")[0]
    fireEvent.click(closeBtn)
    expect(onClose).toHaveBeenCalled()
  })

  it("switches tab via autoSwitchToTab prop", () => {
    const { rerender } = render(
      <ContextPanel
        projectId={42}
        activeThreadId="thread-99"
        autoSwitchToTab="knowledge"
      />,
    )

    expect(screen.getByTestId("context-tab")).toBeInTheDocument()

    // Switch to plan
    rerender(
      <ContextPanel
        projectId={42}
        activeThreadId="thread-99"
        autoSwitchToTab="plan"
      />,
    )

    expect(screen.getByTestId("activity-tab")).toBeInTheDocument()
  })
})
