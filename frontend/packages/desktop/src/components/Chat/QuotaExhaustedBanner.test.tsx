import { render, screen } from "@testing-library/react"
import { describe, it, expect } from "vitest"
import { QuotaExhaustedBanner } from "./QuotaExhaustedBanner"
import { useAgentStore } from "@/stores/agentStore"

describe("QuotaExhaustedBanner", () => {
  it("renders nothing when status is not quota_exhausted", () => {
    useAgentStore.setState({ status: "idle", quotaExhaustedInfo: null })
    const { container } = render(<QuotaExhaustedBanner />)
    expect(container).toBeEmptyDOMElement()
  })

  it("renders banner when status is quota_exhausted with fallback text", () => {
    useAgentStore.setState({ status: "quota_exhausted", quotaExhaustedInfo: null })
    render(<QuotaExhaustedBanner />)

    expect(screen.getByText("chat.quota.banner.title")).toBeInTheDocument()
    expect(screen.getByText(/- chat\.quota\.banner\.message/)).toBeInTheDocument()
  })

  it("renders custom quotaInfo title and message if present", () => {
    useAgentStore.setState({
      status: "quota_exhausted",
      quotaExhaustedInfo: {
        title: "Claude 额度用完",
        message: "当前账号已达到本月调用限制",
      } as any,
    })
    render(<QuotaExhaustedBanner />)

    expect(screen.getByText("Claude 额度用完")).toBeInTheDocument()
    expect(screen.getByText(/- 当前账号已达到本月调用限制/)).toBeInTheDocument()
  })
})
