import { describe, it, expect, vi, beforeEach } from "vitest"
import { renderHook, waitFor } from "@testing-library/react"
import { useAccessibilityPermission } from "../useAccessibilityPermission"

// Mock Tauri API
const mockInvoke = vi.fn()
vi.mock("@tauri-apps/api/core", () => ({
  invoke: (...args: any[]) => mockInvoke(...args),
}))

describe("useAccessibilityPermission", () => {
  beforeEach(() => {
    vi.clearAllMocks()
    // Reset window.__TAURI__
    ;(window as any).__TAURI__ = undefined
  })

  it("should initialize with null permission state", () => {
    const { result } = renderHook(() => useAccessibilityPermission())
    expect(result.current.hasPermission).toBeNull()
  })

  it("should check permission successfully on macOS", async () => {
    mockInvoke.mockResolvedValueOnce(true)
    ;(window as any).__TAURI__ = {}

    const { result } = renderHook(() => useAccessibilityPermission())

    // Wait for useEffect to run
    await waitFor(() => {
      expect(result.current.hasPermission).toBe(true)
    })

    expect(mockInvoke).toHaveBeenCalledWith("check_accessibility_permission")
  })

  it("should handle permission denial", async () => {
    mockInvoke.mockResolvedValueOnce(false)
    ;(window as any).__TAURI__ = {}

    const { result } = renderHook(() => useAccessibilityPermission())

    await waitFor(() => {
      expect(result.current.hasPermission).toBe(false)
    })
  })

  it("should fallback to true when not in Tauri", async () => {
    mockInvoke.mockRejectedValueOnce(new Error("Not in Tauri"))

    const { result } = renderHook(() => useAccessibilityPermission())

    await waitFor(() => {
      expect(result.current.hasPermission).toBe(true)
    })
  })

  it("should request permission on macOS", async () => {
    mockInvoke.mockResolvedValueOnce(true)
    ;(window as any).__TAURI__ = {}

    const { result } = renderHook(() => useAccessibilityPermission())

    await waitFor(() => {
      expect(result.current.hasPermission).toBe(true)
    })

    // Request permission
    await result.current.requestPermission()

    expect(mockInvoke).toHaveBeenCalledWith("open_accessibility_settings")
  })

  it("should not request permission when not in Tauri", async () => {
    const { result } = renderHook(() => useAccessibilityPermission())

    await result.current.requestPermission()

    expect(mockInvoke).not.toHaveBeenCalledWith("open_accessibility_settings")
  })

  it("should recheck permission on window focus", async () => {
    mockInvoke.mockResolvedValue(true)
    ;(window as any).__TAURI__ = {}

    renderHook(() => useAccessibilityPermission())

    // Wait for initial check
    await waitFor(() => {
      expect(mockInvoke).toHaveBeenCalledTimes(1)
    })

    // Simulate focus event
    window.dispatchEvent(new Event("focus"))

    await waitFor(() => {
      expect(mockInvoke).toHaveBeenCalledTimes(2)
    })
  })

  it("should cleanup event listener on unmount", async () => {
    const removeEventListenerSpy = vi.spyOn(window, "removeEventListener")

    const { unmount } = renderHook(() => useAccessibilityPermission())

    unmount()

    expect(removeEventListenerSpy).toHaveBeenCalledWith("focus", expect.any(Function))
  })

  it("should handle checkPermission manually", async () => {
    mockInvoke.mockResolvedValueOnce(true)
    ;(window as any).__TAURI__ = {}

    const { result } = renderHook(() => useAccessibilityPermission())

    const permission = await result.current.checkPermission()

    expect(permission).toBe(true)
    expect(result.current.hasPermission).toBe(true)
  })
})
