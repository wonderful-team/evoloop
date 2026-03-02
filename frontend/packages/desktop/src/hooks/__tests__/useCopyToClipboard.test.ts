import { describe, it, expect, vi, beforeEach } from "vitest"
import { renderHook, act } from "@testing-library/react"
import useCopyToClipboard from "../useCopyToClipboard"

describe("useCopyToClipboard", () => {
  const mockWriteText = vi.fn()

  beforeEach(() => {
    vi.clearAllMocks()
    Object.assign(navigator, {
      clipboard: {
        writeText: mockWriteText,
      },
    })
  })

  it("should initialize with isCopied as false", () => {
    const { result } = renderHook(() => useCopyToClipboard())
    expect(result.current.isCopied).toBe(false)
  })

  it("should copy text to clipboard successfully", async () => {
    mockWriteText.mockResolvedValueOnce(undefined)
    const { result } = renderHook(() => useCopyToClipboard())

    await act(async () => {
      await result.current.copyToClipboard("test text")
    })

    expect(mockWriteText).toHaveBeenCalledWith("test text")
    expect(result.current.isCopied).toBe(true)
  })

  it("should reset isCopied after timeout", async () => {
    vi.useFakeTimers()
    mockWriteText.mockResolvedValueOnce(undefined)
    const { result } = renderHook(() => useCopyToClipboard())

    await act(async () => {
      await result.current.copyToClipboard("test text")
    })

    expect(result.current.isCopied).toBe(true)

    act(() => {
      vi.advanceTimersByTime(2000)
    })

    expect(result.current.isCopied).toBe(false)
    vi.useRealTimers()
  })

  it("should handle clipboard error gracefully", async () => {
    const consoleError = vi.spyOn(console, "error").mockImplementation(() => {})
    mockWriteText.mockRejectedValueOnce(new Error("Clipboard error"))
    const { result } = renderHook(() => useCopyToClipboard())

    await act(async () => {
      await result.current.copyToClipboard("test text")
    })

    expect(result.current.isCopied).toBe(false)
    expect(consoleError).toHaveBeenCalledWith("Failed to copy:", expect.any(Error))
    consoleError.mockRestore()
  })

  it("should handle missing clipboard API", async () => {
    const consoleError = vi.spyOn(console, "error").mockImplementation(() => {})
    // @ts-expect-error - Testing undefined clipboard
    navigator.clipboard = undefined
    const { result } = renderHook(() => useCopyToClipboard())

    await act(async () => {
      await result.current.copyToClipboard("test text")
    })

    expect(result.current.isCopied).toBe(false)
    consoleError.mockRestore()
  })
})
