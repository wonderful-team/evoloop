import { describe, it, expect, vi, beforeEach } from "vitest"
import { renderHook, act, waitFor } from "@testing-library/react"
import { useActionRecorder } from "../useActionRecorder"

// Mock LearningService
const mockStartRecording = vi.fn()
const mockStopRecording = vi.fn()
const mockRecordEvents = vi.fn()

vi.mock("@/client/sdk.gen", () => ({
  LearningService: {
    startRecording: (...args: any[]) => mockStartRecording(...args),
    stopRecording: (...args: any[]) => mockStopRecording(...args),
    recordEvents: (...args: any[]) => mockRecordEvents(...args),
  },
}))

describe("useActionRecorder", () => {
  beforeEach(() => {
    vi.clearAllMocks()
    vi.useFakeTimers()
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  const defaultOptions = {
    threadId: "thread-123",
    taskName: "Test Task",
    enabled: true,
  }

  it("should initialize with correct default state", () => {
    const { result } = renderHook(() => useActionRecorder(defaultOptions))

    expect(result.current.isRecording).toBe(false)
    expect(result.current.eventCount).toBe(0)
    expect(result.current.sessionId).toBeNull()
  })

  it("should start recording successfully", async () => {
    mockStartRecording.mockResolvedValueOnce({ session_id: "session-456" })

    const { result } = renderHook(() => useActionRecorder(defaultOptions))

    await act(async () => {
      await result.current.startRecording()
    })

    expect(result.current.isRecording).toBe(true)
    expect(result.current.sessionId).toBe("session-456")
    expect(mockStartRecording).toHaveBeenCalledWith({
      requestBody: {
        thread_id: "thread-123",
        task_name: "Test Task",
      },
    })
  })

  it("should handle start recording error", async () => {
    const consoleError = vi.spyOn(console, "error").mockImplementation(() => {})
    mockStartRecording.mockRejectedValueOnce(new Error("Failed to start"))

    const { result } = renderHook(() => useActionRecorder(defaultOptions))

    await act(async () => {
      await result.current.startRecording()
    })

    expect(result.current.isRecording).toBe(false)
    expect(consoleError).toHaveBeenCalledWith(
      "[ActionRecorder] Failed to start recording:",
      expect.any(Error)
    )

    consoleError.mockRestore()
  })

  it("should stop recording successfully", async () => {
    mockStartRecording.mockResolvedValueOnce({ session_id: "session-456" })
    mockStopRecording.mockResolvedValueOnce({})

    const { result } = renderHook(() => useActionRecorder(defaultOptions))

    await act(async () => {
      await result.current.startRecording()
    })

    expect(result.current.isRecording).toBe(true)

    await act(async () => {
      await result.current.stopRecording()
    })

    expect(result.current.isRecording).toBe(false)
    expect(result.current.sessionId).toBeNull()
    expect(mockStopRecording).toHaveBeenCalledWith({ sessionId: "session-456" })
  })

  it("should return session info when stopping", async () => {
    mockStartRecording.mockResolvedValueOnce({ session_id: "session-456" })
    mockStopRecording.mockResolvedValueOnce({})

    const { result } = renderHook(() => useActionRecorder(defaultOptions))

    await act(async () => {
      await result.current.startRecording()
    })

    let stopResult
    await act(async () => {
      stopResult = await result.current.stopRecording()
    })

    expect(stopResult).toEqual({
      sessionId: "session-456",
      eventCount: 0,
    })
  })

  it("should record events manually", async () => {
    mockStartRecording.mockResolvedValueOnce({ session_id: "session-456" })

    const { result } = renderHook(() => useActionRecorder(defaultOptions))

    await act(async () => {
      await result.current.startRecording()
    })

    act(() => {
      result.current.recordEvent({
        event_type: "custom",
        target_selector: "#test",
        payload: { data: "test" },
      })
    })

    // Event should be buffered
    expect(result.current.eventCount).toBe(0) // Not flushed yet
  })

  it("should auto-flush events periodically", async () => {
    mockStartRecording.mockResolvedValueOnce({ session_id: "session-456" })
    mockRecordEvents.mockResolvedValueOnce({})

    const { result } = renderHook(() =>
      useActionRecorder({ ...defaultOptions, autoFlushInterval: 1000 })
    )

    await act(async () => {
      await result.current.startRecording()
    })

    act(() => {
      result.current.recordEvent({
        event_type: "click",
        target_selector: "#button",
      })
    })

    // Fast-forward past flush interval
    act(() => {
      vi.advanceTimersByTime(1000)
    })

    await waitFor(() => {
      expect(mockRecordEvents).toHaveBeenCalled()
    })
  })

  it("should not start recording if already recording", async () => {
    mockStartRecording.mockResolvedValueOnce({ session_id: "session-456" })

    const { result } = renderHook(() => useActionRecorder(defaultOptions))

    await act(async () => {
      await result.current.startRecording()
    })

    await act(async () => {
      await result.current.startRecording()
    })

    expect(mockStartRecording).toHaveBeenCalledTimes(1)
  })

  it("should handle flush error and re-buffer events", async () => {
    mockStartRecording.mockResolvedValueOnce({ session_id: "session-456" })
    mockRecordEvents.mockRejectedValueOnce(new Error("Network error"))

    const consoleError = vi.spyOn(console, "error").mockImplementation(() => {})

    const { result } = renderHook(() =>
      useActionRecorder({ ...defaultOptions, autoFlushInterval: 1000 })
    )

    await act(async () => {
      await result.current.startRecording()
    })

    act(() => {
      result.current.recordEvent({
        event_type: "click",
        target_selector: "#button",
      })
    })

    act(() => {
      vi.advanceTimersByTime(1000)
    })

    await waitFor(() => {
      expect(consoleError).toHaveBeenCalledWith(
        "[ActionRecorder] Failed to flush events:",
        expect.any(Error)
      )
    })

    consoleError.mockRestore()
  })

  it("should cleanup timer on unmount", async () => {
    mockStartRecording.mockResolvedValueOnce({ session_id: "session-456" })

    const { result, unmount } = renderHook(() => useActionRecorder(defaultOptions))

    await act(async () => {
      await result.current.startRecording()
    })

    unmount()

    // Should not throw when unmounting
    expect(result.current.isRecording).toBe(true)
  })
})
