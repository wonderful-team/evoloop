import { render, screen, fireEvent } from "@testing-library/react"
import { describe, it, expect, vi } from "vitest"
import { QuotaExhaustedCard } from "./QuotaExhaustedCard"
import { useAgentStore } from "@/stores/agentStore"
import { useChatStore } from "@/stores/chatStore"

const mockNavigate = vi.fn()
vi.mock("@tanstack/react-router", () => ({
  useNavigate: () => mockNavigate,
}))

describe("QuotaExhaustedCard", () => {
  it("renders null if status is not quota_exhausted", () => {
    useAgentStore.setState({ status: "idle", quotaExhaustedInfo: null })
    const { container } = render(<QuotaExhaustedCard />)
    expect(container).toBeEmptyDOMElement()
  })

  it("renders card content and handles navigation & continue action", () => {
    const sendMessageSpy = vi.fn().mockResolvedValue(undefined)
    useChatStore.setState({ sendMessage: sendMessageSpy })
    useAgentStore.setState({
      status: "quota_exhausted",
      quotaExhaustedInfo: {
        title: "额度耗尽",
        message: "额度已用尽，请续费",
        hint: "提示：充值后点击继续即可恢复会话",
      } as any,
    })

    render(<QuotaExhaustedCard />)

    expect(screen.getByText("额度耗尽")).toBeInTheDocument()
    expect(screen.getByText("额度已用尽，请续费")).toBeInTheDocument()
    expect(screen.getByText("提示：充值后点击继续即可恢复会话")).toBeInTheDocument()

    // Click Check Quota
    fireEvent.click(screen.getByText("chat.quota.card.checkQuota"))
    expect(mockNavigate).toHaveBeenCalledWith({ to: "/subscription" })

    // Click Continue
    fireEvent.click(screen.getByText("chat.quota.card.continue"))
    expect(sendMessageSpy).toHaveBeenCalledWith("chat.quota.continuePrompt")
  })
})
