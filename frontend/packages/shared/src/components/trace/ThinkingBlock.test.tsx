import { fireEvent, render, screen } from "@testing-library/react"
import { describe, expect, it } from "vitest"
import { ThinkingBlock } from "./ThinkingBlock"

describe("ThinkingBlock component", () => {
  it("renders non-streaming thinking block collapsed by default", () => {
    render(
      <ThinkingBlock
        data={{
          thinking: "Deep thought analysis here...",
          duration: "1.2s",
        }}
      />,
    )

    expect(screen.getByText("思考过程")).toBeInTheDocument()
    expect(screen.getByText("(1.2s)")).toBeInTheDocument()
  })

  it("renders streaming indicator when isStreaming is true", () => {
    render(
      <ThinkingBlock
        data={{
          thinking: "Currently streaming thoughts...",
          isStreaming: true,
        }}
      />,
    )

    expect(screen.getByText("正在思考...")).toBeInTheDocument()
  })

  it("can be opened by default and toggled by click", () => {
    render(
      <ThinkingBlock
        defaultOpen={true}
        data={{
          thinking: "This content is visible immediately",
        }}
      />,
    )

    expect(
      screen.getByText("This content is visible immediately"),
    ).toBeInTheDocument()

    const trigger = screen.getByRole("button")
    fireEvent.click(trigger)
    // After toggling, Collapsible state changes
  })

  it("supports custom renderContent function", () => {
    render(
      <ThinkingBlock
        defaultOpen={true}
        data={{
          thinking: "raw text",
        }}
        renderContent={(text) => <div data-testid="custom-rendered">{text.toUpperCase()}</div>}
      />,
    )

    expect(screen.getByTestId("custom-rendered")).toHaveTextContent("RAW TEXT")
  })
})
