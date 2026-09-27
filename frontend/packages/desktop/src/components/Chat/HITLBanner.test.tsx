import { render, screen } from "@testing-library/react"
import { beforeEach, describe, expect, it } from "vitest"
import { HITL_STATUS } from "@/stores/agent/hitlConstants"
import { useAgentStore } from "@/stores/agentStore"
import { HITLBanner } from "./HITLBanner"

describe("HITLBanner component", () => {
  beforeEach(() => {
    useAgentStore.setState({
      status: "idle" as any,
      humanRequest: null,
    })
  })

  it("returns null when status is not interrupted", () => {
    const { container } = render(<HITLBanner />)
    expect(container.firstChild).toBeNull()
  })

  it("returns null when interrupted but humanRequest is null", () => {
    useAgentStore.setState({
      status: HITL_STATUS.interrupted as any,
      humanRequest: null,
    })

    const { container } = render(<HITLBanner />)
    expect(container.firstChild).toBeNull()
  })

  it("renders warning banner when interrupted and humanRequest is present", () => {
    useAgentStore.setState({
      status: HITL_STATUS.interrupted as any,
      humanRequest: {
        id: "req-1",
        type: "approval",
        prompt: "是否授权执行？",
      } as any,
    })

    render(<HITLBanner />)
    expect(screen.getByText("chat.hitl.waiting")).toBeInTheDocument()
  })
})
