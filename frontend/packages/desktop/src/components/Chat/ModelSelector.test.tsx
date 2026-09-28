import { render, screen, waitFor } from "@testing-library/react"
import { describe, it, expect, vi, beforeEach } from "vitest"
import { ModelSelector } from "./ModelSelector"
import { llmPlatformService } from "@/services/llmPlatform"
import * as useAuthModule from "@/hooks/useAuth"

describe("ModelSelector", () => {
  beforeEach(() => {
    vi.clearAllMocks()
    vi.spyOn(useAuthModule, "isLoggedIn").mockReturnValue(true)
  })

  it("fetches and displays models for authenticated user", async () => {
    const mockModels = [
      {
        id: "gpt-4o",
        name: "GPT-4o",
        type: "platform" as const,
        capabilities: ["chat"],
      },
      {
        id: "deepseek-coder",
        name: "DeepSeek Coder",
        type: "custom" as const,
        provider: "deepseek",
        capabilities: ["chat"],
      },
      {
        id: "qwen-local",
        name: "Qwen 2.5 7B",
        type: "custom" as const,
        provider: "ollama",
        capabilities: ["chat"],
      },
    ]

    vi.spyOn(llmPlatformService, "fetchModels").mockResolvedValue(mockModels as any)

    const onChange = vi.fn()
    render(<ModelSelector value="gpt-4o" onChange={onChange} />)

    await waitFor(() => {
      expect(llmPlatformService.fetchModels).toHaveBeenCalledTimes(1)
    })

    // Selected model name shown
    expect(screen.getByText("GPT-4o")).toBeInTheDocument()
  })

  it("does not fetch models if user is not logged in", async () => {
    vi.spyOn(useAuthModule, "isLoggedIn").mockReturnValue(false)
    const fetchSpy = vi.spyOn(llmPlatformService, "fetchModels").mockResolvedValue([])

    render(<ModelSelector value={null} onChange={vi.fn()} />)

    expect(fetchSpy).not.toHaveBeenCalled()
    expect(screen.getByText("chat.modelSelector.placeholder")).toBeInTheDocument()
  })

  it("renders disabled state when disabled prop is true", () => {
    vi.spyOn(llmPlatformService, "fetchModels").mockResolvedValue([])
    render(<ModelSelector value={null} onChange={vi.fn()} disabled={true} />)

    const trigger = screen.getByRole("combobox")
    expect(trigger).toBeDisabled()
  })
})
