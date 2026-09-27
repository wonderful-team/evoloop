import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { renderHook, waitFor } from "@testing-library/react"
import type { PropsWithChildren } from "react"
import { beforeEach, describe, expect, it, vi } from "vitest"

import { SystemService } from "@/client"
import useAuth from "@/hooks/useAuth"
import {
  markSetupCompleted,
  resetSetupCompleted,
  useSetupRequired,
} from "./useSetupRequired"

vi.mock("@/hooks/useAuth", () => ({
  default: vi.fn(),
}))

vi.mock("@/client", () => ({
  SystemService: {
    getSystemConfig: vi.fn(),
  },
}))

function makeConfig(
  items: Array<[string, string]>,
): Array<{ key: string; value: string }> {
  return items.map(([key, value]) => ({ key, value }))
}

function useRealLocalStorage() {
  const store = new Map<string, string>()
  Object.defineProperty(window, "localStorage", {
    value: {
      getItem: (k: string) => store.get(k) ?? null,
      setItem: (k: string, v: string) => store.set(k, v),
      removeItem: (k: string) => store.delete(k),
      clear: () => store.clear(),
    },
    configurable: true,
  })
}

function setup() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  })
  const wrapper = ({ children }: PropsWithChildren) => (
    <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
  )
  return { wrapper, queryClient }
}

describe("useSetupRequired", () => {
  beforeEach(() => {
    useRealLocalStorage()
    resetSetupCompleted()
    vi.clearAllMocks()
    ;(useAuth as unknown as ReturnType<typeof vi.fn>).mockReturnValue({
      user: { id: 1 },
    })
  })

  it("reports loading while config is still being fetched", async () => {
    const { wrapper } = setup()
    ;(
      SystemService.getSystemConfig as unknown as ReturnType<typeof vi.fn>
    ).mockReturnValue(new Promise(() => {}))
    const { result } = renderHook(() => useSetupRequired(), { wrapper })
    expect(result.current.loading).toBe(true)
    expect(result.current.required).toBe(false)
  })

  it("platform mode with no LLM_MODEL does not require the wizard", async () => {
    const { wrapper } = setup()
    ;(
      SystemService.getSystemConfig as unknown as ReturnType<typeof vi.fn>
    ).mockResolvedValue(
      makeConfig([
        ["LLM_CONFIG_TYPE", "platform"],
        ["WORKSPACE_ROOT", "/Projects"],
      ]),
    )
    const { result } = renderHook(() => useSetupRequired(), { wrapper })
    await waitFor(() => expect(result.current.loading).toBe(false))
    expect(result.current.required).toBe(false)
    expect(result.current.missingItems.llm).toBe(false)
  })

  it("platform mode ignores a stale LLM_MODEL", async () => {
    const { wrapper } = setup()
    ;(
      SystemService.getSystemConfig as unknown as ReturnType<typeof vi.fn>
    ).mockResolvedValue(
      makeConfig([
        ["LLM_CONFIG_TYPE", "platform"],
        ["LLM_MODEL", "deepseek-v4-flash"],
      ]),
    )
    const { result } = renderHook(() => useSetupRequired(), { wrapper })
    await waitFor(() => expect(result.current.loading).toBe(false))
    expect(result.current.missingItems.llm).toBe(false)
  })

  it("custom mode without model+base_url requires the wizard", async () => {
    const { wrapper } = setup()
    ;(
      SystemService.getSystemConfig as unknown as ReturnType<typeof vi.fn>
    ).mockResolvedValue(
      makeConfig([
        ["LLM_CONFIG_TYPE", "custom"],
        ["LLM_MODEL", "gpt-4o"],
        ["WORKSPACE_ROOT", "/Projects"],
      ]),
    )
    const { result } = renderHook(() => useSetupRequired(), { wrapper })
    await waitFor(() => expect(result.current.loading).toBe(false))
    expect(result.current.missingItems.llm).toBe(true)
    expect(result.current.required).toBe(true)
  })

  it("complete custom config does not require the wizard", async () => {
    const { wrapper } = setup()
    ;(
      SystemService.getSystemConfig as unknown as ReturnType<typeof vi.fn>
    ).mockResolvedValue(
      makeConfig([
        ["LLM_CONFIG_TYPE", "custom"],
        ["LLM_MODEL", "gpt-4o"],
        ["LLM_BASE_URL", "https://api.openai.com"],
        ["WORKSPACE_ROOT", "/Projects"],
      ]),
    )
    const { result } = renderHook(() => useSetupRequired(), { wrapper })
    await waitFor(() => expect(result.current.loading).toBe(false))
    expect(result.current.missingItems.llm).toBe(false)
    expect(result.current.required).toBe(false)
  })

  it("requires the wizard when WORKSPACE_ROOT is missing", async () => {
    const { wrapper } = setup()
    ;(
      SystemService.getSystemConfig as unknown as ReturnType<typeof vi.fn>
    ).mockResolvedValue(makeConfig([["LLM_CONFIG_TYPE", "platform"]]))
    const { result } = renderHook(() => useSetupRequired(), { wrapper })
    await waitFor(() => expect(result.current.loading).toBe(false))
    expect(result.current.missingItems.workspaceRoot).toBe(true)
    expect(result.current.required).toBe(true)
  })

  it("does not require the wizard once setup was completed", async () => {
    markSetupCompleted()
    const { wrapper } = setup()
    ;(
      SystemService.getSystemConfig as unknown as ReturnType<typeof vi.fn>
    ).mockResolvedValue(makeConfig([["LLM_CONFIG_TYPE", "platform"]]))
    const { result } = renderHook(() => useSetupRequired(), { wrapper })
    await waitFor(() => expect(result.current.loading).toBe(false))
    expect(result.current.required).toBe(false)
    expect(result.current.missingItems.workspaceRoot).toBe(true)
  })
})
