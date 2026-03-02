import { describe, it, expect, vi, beforeEach } from "vitest"
import { renderHook, waitFor } from "@testing-library/react"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import useAuth from "../useAuth"

// Mock the gateway
vi.mock("@/lib/gateway", () => ({
  evoLoopGateway: {
    login: vi.fn(),
    logout: vi.fn(),
    getCurrentMember: vi.fn(),
  },
}))

// Mock localStorage
const localStorageMock = {
  getItem: vi.fn(),
  setItem: vi.fn(),
  removeItem: vi.fn(),
  clear: vi.fn(),
}
Object.defineProperty(window, "localStorage", {
  value: localStorageMock,
})

import { evoLoopGateway } from "@/lib/gateway"

const createWrapper = () => {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: {
        retry: false,
      },
    },
  })
  return ({ children }: { children: React.ReactNode }) => (
    <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
  )
}

describe("useAuth (Mobile)", () => {
  beforeEach(() => {
    vi.clearAllMocks()
    localStorageMock.getItem.mockReturnValue(null)
  })

  describe("initialization", () => {
    it("should check for existing token on mount", () => {
      localStorageMock.getItem.mockReturnValue("test-token")
      ;(evoLoopGateway.getCurrentMember as ReturnType<typeof vi.fn>).mockResolvedValueOnce({
        id: 1,
        username: "testuser",
      })

      renderHook(() => useAuth(), {
        wrapper: createWrapper(),
      })

      expect(localStorageMock.getItem).toHaveBeenCalledWith("evoloop_token")
    })

    it("should return not authenticated when no token", () => {
      localStorageMock.getItem.mockReturnValue(null)

      const { result } = renderHook(() => useAuth(), {
        wrapper: createWrapper(),
      })

      expect(result.current.isAuthenticated).toBe(false)
      expect(result.current.isLoading).toBe(false)
    })
  })

  describe("login", () => {
    it("should login successfully", async () => {
      const mockMember = {
        member_id: "1",
        username: "testuser",
        nickname: "Test User",
        avatar: "https://example.com/avatar.png",
      }

      ;(evoLoopGateway.login as ReturnType<typeof vi.fn>).mockResolvedValueOnce({
        member_id: "1",
        token: "test-token",
      })
      ;(evoLoopGateway.getCurrentMember as ReturnType<typeof vi.fn>).mockResolvedValueOnce(mockMember)

      const { result } = renderHook(() => useAuth(), {
        wrapper: createWrapper(),
      })

      await result.current.login({
        username: "testuser",
        password: "password123",
      })

      await waitFor(() => {
        expect(result.current.isAuthenticated).toBe(true)
      })

      expect(localStorageMock.setItem).toHaveBeenCalledWith("evoloop_token", "test-token")
      expect(localStorageMock.setItem).toHaveBeenCalledWith("evoloop_member_id", "1")
    })

    it("should handle login error", async () => {
      const error = new Error("Invalid credentials")
      ;(evoLoopGateway.login as ReturnType<typeof vi.fn>).mockRejectedValueOnce(error)

      const { result } = renderHook(() => useAuth(), {
        wrapper: createWrapper(),
      })

      const consoleError = vi.spyOn(console, "error").mockImplementation(() => {})

      await result.current.login({
        username: "testuser",
        password: "wrongpassword",
      })

      expect(result.current.isAuthenticated).toBe(false)
      expect(localStorageMock.setItem).not.toHaveBeenCalled()

      consoleError.mockRestore()
    })
  })

  describe("logout", () => {
    it("should logout successfully", async () => {
      localStorageMock.getItem.mockReturnValue("test-token")
      ;(evoLoopGateway.getCurrentMember as ReturnType<typeof vi.fn>).mockResolvedValueOnce({
        id: 1,
        username: "testuser",
      })
      ;(evoLoopGateway.logout as ReturnType<typeof vi.fn>).mockResolvedValueOnce(undefined)

      const { result } = renderHook(() => useAuth(), {
        wrapper: createWrapper(),
      })

      // Wait for initial auth check
      await waitFor(() => {
        expect(result.current.isAuthenticated).toBe(true)
      })

      await result.current.logout()

      expect(localStorageMock.removeItem).toHaveBeenCalledWith("evoloop_token")
      expect(localStorageMock.removeItem).toHaveBeenCalledWith("evoloop_member_id")
      expect(result.current.isAuthenticated).toBe(false)
      expect(result.current.member).toBeNull()
    })
  })

  describe("member data", () => {
    it("should fetch member data when authenticated", async () => {
      localStorageMock.getItem.mockImplementation((key: string) => {
        if (key === "evoloop_token") return "test-token"
        if (key === "evoloop_member_id") return "1"
        return null
      })

      const mockMember = {
        member_id: "1",
        username: "testuser",
        nickname: "Test User",
        avatar: "https://example.com/avatar.png",
      }

      ;(evoLoopGateway.getCurrentMember as ReturnType<typeof vi.fn>).mockResolvedValueOnce(mockMember)

      const { result } = renderHook(() => useAuth(), {
        wrapper: createWrapper(),
      })

      await waitFor(() => {
        expect(result.current.member).toEqual(mockMember)
      })

      expect(result.current.isAuthenticated).toBe(true)
    })
  })
})
