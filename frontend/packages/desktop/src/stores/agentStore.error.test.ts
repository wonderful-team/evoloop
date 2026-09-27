import {beforeEach, describe, expect, it, vi} from "vitest"

import {useAgentStore} from "./agentStore"
import {toast} from "sonner"

vi.mock("@evoloop/shared/i18n", () => ({
  default: { t: (key: string) => `#${key}#` },
}))

vi.mock("sonner", () => ({
  toast: { error: vi.fn(), info: vi.fn(), success: vi.fn() },
}))

vi.mock("@/client", () => ({
  AgentService: { chatEndpoint: vi.fn() },
}))

describe("agentStore._handleServerError 分发中枢", () => {
  beforeEach(() => {
    vi.mocked(toast.error).mockClear()
    useAgentStore.setState({ status: "running", quotaExhaustedInfo: null })
  })

  it("quota_exhausted → 套餐横幅状态 + info 落 store", () => {
    useAgentStore
      .getState()
      ._handleServerError({
        type: "quota_exhausted",
        title: "T",
        message: "M",
        hint: "H",
      })

    const state = useAgentStore.getState()
    expect(state.status).toBe("quota_exhausted")
    expect(state.quotaExhaustedInfo).toMatchObject({
      title: "T",
      message: "M",
      hint: "H",
    })
  })

  it("llm_auth_error → status=error + toast（标题/描述来自事件）", () => {
    useAgentStore
      .getState()
      ._handleServerError({
        type: "llm_auth_error",
        title: "Auth",
        message: "bad key",
      })

    expect(useAgentStore.getState().status).toBe("error")
    expect(toast.error).toHaveBeenCalledWith(
      "Auth",
      expect.objectContaining({ description: "bad key" }),
    )
  })

  it("auth_expired → status=error + toast", () => {
    useAgentStore
      .getState()
      ._handleServerError({ type: "auth_expired", message: "expired" })

    expect(useAgentStore.getState().status).toBe("error")
    expect(toast.error).toHaveBeenCalledWith("expired", { duration: 8000 })
  })

  it("未知类型 → 走连接错误兜底（toast + status=error）", () => {
    useAgentStore
      .getState()
      ._handleServerError({ type: "something_new", message: "boom" })

    expect(useAgentStore.getState().status).toBe("error")
    expect(toast.error).toHaveBeenCalled()
  })

  it("quota 缺省字段时用 i18n 兜底文案", () => {
    useAgentStore.getState()._handleServerError({ type: "quota_exhausted" })

    expect(useAgentStore.getState().quotaExhaustedInfo).toMatchObject({
      title: "#chat.quotaExhausted.title#",
      message: "#chat.quotaExhausted.message#",
      hint: "#chat.quotaExhausted.hint#",
    })
  })
})
