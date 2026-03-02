import { describe, it, expect, vi, beforeEach } from "vitest"
import { renderHook, waitFor } from "@testing-library/react"
import useMemberCancellation from "../useMemberCancellation"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"

// Mock the gateway
vi.mock("@/lib/gateway", () => ({
  evoLoopGateway: {
    cancelMembership: vi.fn(),
  },
}))

import { evoLoopGateway } from "@/lib/gateway"

const createWrapper = () => {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: { retry: false },
      mutations: { retry: false },
    },
  })
  return ({ children }: { children: React.ReactNode }) => (
    <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
  )
}

describe("useMemberCancellation", () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it("should initialize with correct default state", () => {
    const { result } = renderHook(() => useMemberCancellation(), {
      wrapper: createWrapper(),
    })

    expect(result.current.cancelMembership).toBeDefined()
    expect(result.current.isCancelling).toBe(false)
  })

  it("should cancel membership successfully", async () => {
    const mockResponse = { success: true, message: "Membership cancelled" }
    ;(evoLoopGateway.cancelMembership as ReturnType<typeof vi.fn>).mockResolvedValueOnce(mockResponse)

    const { result } = renderHook(() => useMemberCancellation(), {
      wrapper: createWrapper(),
    })

    result.current.cancelMembership.mutate({ reason: "No longer needed" })

    await waitFor(() => {
      expect(result.current.cancelMembership.isSuccess).toBe(true)
    })

    expect(evoLoopGateway.cancelMembership).toHaveBeenCalledWith({ reason: "No longer needed" })
  })

  it("should handle cancellation error", async () => {
    const error = new Error("Cancellation failed")
    ;(evoLoopGateway.cancelMembership as ReturnType<typeof vi.fn>).mockRejectedValueOnce(error)

    const { result } = renderHook(() => useMemberCancellation(), {
      wrapper: createWrapper(),
    })

    result.current.cancelMembership.mutate({ reason: "Test" })

    await waitFor(() => {
      expect(result.current.cancelMembership.isError).toBe(true)
    })
  })

  it("should show loading state during cancellation", async () => {
    let resolvePromise: (value: unknown) => void
    const promise = new Promise((resolve) => {
      resolvePromise = resolve
    })

    ;(evoLoopGateway.cancelMembership as ReturnType<typeof vi.fn>).mockReturnValueOnce(promise)

    const { result } = renderHook(() => useMemberCancellation(), {
      wrapper: createWrapper(),
    })

    result.current.cancelMembership.mutate({ reason: "Test" })

    expect(result.current.isCancelling).toBe(true)

    resolvePromise!({ success: true })

    await waitFor(() => {
      expect(result.current.cancelMembership.isSuccess).toBe(true)
    })
  })
})
