import { describe, it, expect, vi, beforeEach } from "vitest"
import { renderHook, waitFor } from "@testing-library/react"
import { useScreenRecordingPermission } from "../useScreenRecordingPermission"

const mockInvoke = vi.fn()
vi.mock("@tauri-apps/api/core", () => ({
  invoke: (...args: any[]) => mockInvoke(...args),
}))

describe("useScreenRecordingPermission", () => {
  beforeEach(() => {
    vi.clearAllMocks()
    ;(window as any).__TAURI__ = undefined
  })

  it("should initialize with null permission state", () => {
    const { result } = renderHook(() => useScreenRecordingPermission())
    expect(result.current.hasPermission).toBeNull()
    expect(result.current.isChecking).toBe(true)
  })

  it("should check permission successfully on macOS", async () => {
    mockInvoke.mockResolvedValueOnce(true)
    ;(window as any).__TAURI__ = {}

    const { result } = renderHook(() => useScreenRecordingPermission())

    await waitFor(() => {
      expect(result.current.hasPermission).toBe(true)
    })

    expect(result.current.isChecking).toBe(false)
    expect(mockInvoke).toHaveBeenCalledWith("check_screen_recording_permission")
  })

  it("should handle permission denial", async () => {
    mockInvoke.mockResolvedValueOnce(false)
    ;(window as any).__TAURI__ = {}

    const { result } = renderHook(() => useScreenRecordingPermission())

    await waitFor(() => {
      expect(result.current.hasPermission).toBe(false)
    })
  })

  it("should fallback to true when not in Tauri", async () => {
    mockInvoke.mockRejectedValueOnce(new Error("Not in Tauri"))

    const { result } = renderHook(() => useScreenRecordingPermission())

    await waitFor(() => {
      expect(result.current.hasPermission).toBe(true)
    })
  })

  it("should request permission on macOS", async () => {
    mockInvoke.mockResolvedValueOnce(true)
    ;(window as any).__TAURI__ = {}

    const { result } = renderHook(() => useScreenRecordingPermission())

    await waitFor(() => {
      expect(result.current.hasPermission).toBe(true)
    })

    await result.current.requestPermission()

    expect(mockInvoke).toHaveBeenCalledWith("open_screen_recording_settings")
  })

  it("should not request permission when not in Tauri", async () => {
    const { result } = renderHook(() => useScreenRecordingPermission())

    await result.current.requestPermission()

    expect(mockInvoke).not.toHaveBeenCalledWith("open_screen_recording_settings")
  })

  it("should recheck permission on window focus", async () => {
    mockInvoke.mockResolvedValue(true)
    ;(window as any).__TAURI__ = {}

    renderHook(() => useScreenRecordingPermission())

    await waitFor(() => {
      expect(mockInvoke).toHaveBeenCalledTimes(1)
    })

    window.dispatchEvent(new Event("focus"))

    await waitFor(() => {
      expect(mockInvoke).toHaveBeenCalledTimes(2)
    })
  })
})
