import {render, screen, waitFor} from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import {beforeEach, describe, expect, it, vi} from "vitest"

import {SystemService} from "@/client"
import {ModelSettings} from "./ModelSettings"

vi.mock("@/client", () => ({
  SystemService: {
    discoverModels: vi.fn(),
    getSystemConfig: vi.fn(),
    applyLlmConfig: vi.fn(),
    testLlmConnection: vi.fn(),
  },
}))

vi.mock("./EmbeddingSettings", () => ({
  EmbeddingSettings: () => null,
}))
vi.mock("./LLMSettings", () => ({
  LLMSettings: () => null,
}))

const MOCK_MODELS = [
  {
    id: "evocloud-deepseek-v4",
    name: "DeepSeek V4",
    source: "evocloud",
    status: "available",
    model_name: "deepseek-v4-flash",
    base_url: null,
  },
  {
    id: "lm-local",
    name: "Local LLM",
    source: "lm-studio",
    status: "available",
    model_name: "local-model",
    base_url: "http://localhost:1234/v1",
  },
  {
    id: "custom:gpt-4o",
    name: "gpt-4o (Custom)",
    source: "custom",
    status: "available",
    model_name: "gpt-4o",
    base_url: "https://api.openai.com",
  },
]

function mockConfig(entries: Array<[string, string]> = []) {
  ;(
    SystemService.getSystemConfig as unknown as ReturnType<typeof vi.fn>
  ).mockResolvedValue(entries.map(([key, value]) => ({ key, value })))
}

function mockDiscover() {
  ;(
    SystemService.discoverModels as unknown as ReturnType<typeof vi.fn>
  ).mockResolvedValue({ models: MOCK_MODELS, last_updated: "now" })
}

describe("ModelSettings.saveModel", () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mockDiscover()
    mockConfig()
  })

  it("does NOT call applyLlmConfig when an evocloud (platform) model is selected", async () => {
    render(<ModelSettings />)
    const select = await screen.findByRole("combobox")
    const user = userEvent.setup()

    await user.click(select)
    const option = await screen.findByRole("option", { name: /DeepSeek V4/ })
    await user.click(option)

    await waitFor(() => {
      expect(SystemService.applyLlmConfig).not.toHaveBeenCalled()
    })
  })

  it("persists custom/local models through applyLlmConfig", async () => {
    render(<ModelSettings />)
    const select = await screen.findByRole("combobox")
    const user = userEvent.setup()

    await user.click(select)
    const option = await screen.findByRole("option", { name: /Local LLM/ })
    await user.click(option)

    await waitFor(() => {
      expect(SystemService.applyLlmConfig).toHaveBeenCalledTimes(1)
      const body = (
        SystemService.applyLlmConfig as unknown as ReturnType<typeof vi.fn>
      ).mock.calls[0][0].requestBody
      expect(body).toMatchObject({
        provider: "lm-studio",
        base_url: "http://localhost:1234/v1",
        model: "local-model",
      })
    })
  })

  it("restores the previously saved custom default from CUSTOM_LLM_MODEL", async () => {
    mockConfig([
      ["LLM_CONFIG_TYPE", "custom"],
      ["LLM_MODEL", "gpt-4o"],
      ["CUSTOM_LLM_MODEL", "gpt-4o"],
      ["LLM_BASE_URL", "https://api.openai.com"],
    ])
    render(<ModelSettings />)
    const select = await screen.findByRole("combobox")
    expect(select).toHaveTextContent(/gpt-4o/)
  })
})
