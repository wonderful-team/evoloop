import { render, screen, fireEvent } from "@testing-library/react"
import { describe, it, expect, vi } from "vitest"
import { ChatWelcome } from "./ChatWelcome"
import { useHostContextStore } from "@/stores/hostContextStore"

const mockNavigate = vi.fn()
vi.mock("@tanstack/react-router", () => ({
  useNavigate: () => mockNavigate,
}))

describe("ChatWelcome", () => {
  it("renders wooden robot, standby status, and welcome navigation cards when not connected to host", () => {
    useHostContextStore.setState({ context: null, connected: false })

    render(<ChatWelcome />)

    expect(screen.getByText("chat.welcome.statusStandby")).toBeInTheDocument()
    expect(screen.getByText("chat.welcome.mobileHint")).toBeInTheDocument()

    // Nav buttons are rendered (e.g., WELCOME_NAVS)
    const buttons = screen.getAllByRole("button")
    expect(buttons.length).toBeGreaterThan(0)

    fireEvent.click(buttons[0])
    expect(mockNavigate).toHaveBeenCalled()
  })

  it("renders host context subtitle when host is connected", () => {
    useHostContextStore.setState({
      connected: true,
      context: { pageName: "OrderDetails", route: "/orders/123" } as any,
    })

    render(<ChatWelcome />)

    expect(screen.getByText("chat.welcome.contextSubtitle")).toBeInTheDocument()
    expect(screen.getByText("chat.welcome.hostConnected")).toBeInTheDocument()
  })
})
