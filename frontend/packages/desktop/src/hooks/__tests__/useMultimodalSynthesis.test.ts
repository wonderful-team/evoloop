import { describe, it, expect, vi, beforeEach } from "vitest"
import { renderHook, act, waitFor } from "@testing-library/react"
import { useMultimodalSynthesis, useRecordingWithSynthesis } from "../useMultimodalSynthesis"

// Mock the dependencies
const mockInvoke = vi.fn()
vi.mock("@tauri-apps/api/core", () => ({
  invoke: (...args: any[]) => mockInvoke(...args),
}))

const mockSynthesizeFromRecording = vi.fn()
const mockPreviewRecordingData = vi.fn()

vi.mock("@/client/sdk.gen", () => ({
  LearningService: {
    synthesizeFromRecording: (...args: any[]) => mockSynthesizeFromRecording(...args),
    previewRecordingData: (...args: any[]) => mockPreviewRecordingData(...args),
  },
}))

describe("useMultimodalSynthesis", () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it("should initialize with correct default state", () => {
    const { result } = renderHook(() => useMultimodalSynthesis())

    expect(result.current.isSynthesizing).toBe(false)
    expect(result.current.progress).toBe("")
    expect(result.current.synthesize).toBeDefined()
    expect(result.current.previewRecording).toBeDefined()
  })

  it("should synthesize successfully", async () => {
    const mockResult = {
      success: true,
      skill_id: 123,
      skill_name: "Test Skill",
      processing_time_seconds: 5.2,
      frames_analyzed: 100,
      events_processed: 50,
    }
    mockSynthesizeFromRecording.mockResolvedValueOnce(mockResult)

    const onSuccess = vi.fn()
    const { result } = renderHook(() => useMultimodalSynthesis({ onSuccess }))

    let synthesisResult
    await act(async () => {
      synthesisResult = await result.current.synthesize({
        videoPath: "/path/to/video.mp4",
        sessionId: "session-456",
        taskDescription: "Test task",
      })
    })

    expect(synthesisResult).toEqual(mockResult)
    expect(onSuccess).toHaveBeenCalledWith(mockResult)
    expect(result.current.isSynthesizing).toBe(false)
    expect(mockSynthesizeFromRecording).toHaveBeenCalledWith({
      requestBody: {
        video_path: "/path/to/video.mp4",
        session_id: "session-456",
        task_description: "Test task",
        thread_id: undefined,
      },
    })
  })

  it("should handle synthesis failure", async () => {
    mockSynthesizeFromRecording.mockResolvedValueOnce({
      success: false,
      error: "Processing failed",
    })

    const onError = vi.fn()
    const { result } = renderHook(() => useMultimodalSynthesis({ onError }))

    let synthesisResult
    await act(async () => {
      synthesisResult = await result.current.synthesize({
        videoPath: "/path/to/video.mp4",
        sessionId: "session-456",
        taskDescription: "Test task",
      })
    })

    expect(synthesisResult).toBeNull()
    expect(onError).toHaveBeenCalled()
    expect(result.current.isSynthesizing).toBe(false)
  })

  it("should handle synthesis error", async () => {
    mockSynthesizeFromRecording.mockRejectedValueOnce(new Error("Network error"))

    const onError = vi.fn()
    const { result } = renderHook(() => useMultimodalSynthesis({ onError }))

    let synthesisResult
    await act(async () => {
      synthesisResult = await result.current.synthesize({
        videoPath: "/path/to/video.mp4",
        sessionId: "session-456",
        taskDescription: "Test task",
      })
    })

    expect(synthesisResult).toBeNull()
    expect(onError).toHaveBeenCalledWith(expect.any(Error))
    expect(result.current.isSynthesizing).toBe(false)
  })

  it("should preview recording data", async () => {
    const mockPreview = {
      events: [{ type: "click" }],
      duration: 10.5,
    }
    mockPreviewRecordingData.mockResolvedValueOnce(mockPreview)

    const { result } = renderHook(() => useMultimodalSynthesis())

    const previewResult = await act(async () => {
      return await result.current.previewRecording({
        videoPath: "/path/to/video.mp4",
        sessionId: "session-456",
      })
    })

    expect(previewResult).toEqual(mockPreview)
    expect(mockPreviewRecordingData).toHaveBeenCalledWith({
      sessionId: "session-456",
      videoPath: "/path/to/video.mp4",
    })
  })

  it("should handle preview error", async () => {
    const consoleError = vi.spyOn(console, "error").mockImplementation(() => {})
    mockPreviewRecordingData.mockRejectedValueOnce(new Error("Preview failed"))

    const { result } = renderHook(() => useMultimodalSynthesis())

    const previewResult = await act(async () => {
      return await result.current.previewRecording({
        videoPath: "/path/to/video.mp4",
        sessionId: "session-456",
      })
    })

    expect(previewResult).toBeNull()
    expect(consoleError).toHaveBeenCalledWith("Preview failed:", expect.any(Error))

    consoleError.mockRestore()
  })
})

describe("useRecordingWithSynthesis", () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it("should initialize with correct default state", () => {
    const { result } = renderHook(() => useRecordingWithSynthesis())

    expect(result.current.isRecording).toBe(false)
    expect(result.current.sessionId).toBeNull()
    expect(result.current.videoPath).toBeNull()
    expect(result.current.isSynthesizing).toBe(false)
  })

  it("should start recording", async () => {
    mockInvoke.mockResolvedValueOnce(undefined)

    const { result } = renderHook(() => useRecordingWithSynthesis())

    let sessionId
    await act(async () => {
      sessionId = await result.current.startRecording()
    })

    expect(result.current.isRecording).toBe(true)
    expect(result.current.sessionId).toBe(sessionId)
    expect(mockInvoke).toHaveBeenCalledWith("start_screen_recording")
  })

  it("should stop recording and get video path", async () => {
    mockInvoke
      .mockResolvedValueOnce(undefined) // start
      .mockResolvedValueOnce("/path/to/video.mp4") // stop

    const { result } = renderHook(() => useRecordingWithSynthesis())

    await act(async () => {
      await result.current.startRecording()
    })

    let stopResult
    await act(async () => {
      stopResult = await result.current.stopRecording()
    })

    expect(result.current.isRecording).toBe(false)
    expect(result.current.videoPath).toBe("/path/to/video.mp4")
    expect(stopResult).toEqual({
      sessionId: expect.any(String),
      videoPath: "/path/to/video.mp4",
    })
    expect(mockInvoke).toHaveBeenCalledWith("stop_screen_recording")
  })

  it("should not stop if not recording", async () => {
    const { result } = renderHook(() => useRecordingWithSynthesis())

    const stopResult = await act(async () => {
      return await result.current.stopRecording()
    })

    expect(stopResult).toBeNull()
    expect(mockInvoke).not.toHaveBeenCalled()
  })

  it("should handle stop recording error", async () => {
    mockInvoke
      .mockResolvedValueOnce(undefined) // start
      .mockRejectedValueOnce(new Error("Stop failed")) // stop

    const consoleError = vi.spyOn(console, "error").mockImplementation(() => {})

    const { result } = renderHook(() => useRecordingWithSynthesis())

    await act(async () => {
      await result.current.startRecording()
    })

    const stopResult = await act(async () => {
      return await result.current.stopRecording()
    })

    expect(stopResult).toBeNull()
    expect(consoleError).toHaveBeenCalledWith("Failed to stop recording:", expect.any(Error))

    consoleError.mockRestore()
  })

  it("should synthesize from recording", async () => {
    mockInvoke
      .mockResolvedValueOnce(undefined) // start
      .mockResolvedValueOnce("/path/to/video.mp4") // stop

    const mockResult = {
      success: true,
      skill_id: 123,
      skill_name: "Test Skill",
      processing_time_seconds: 5.2,
      frames_analyzed: 100,
      events_processed: 50,
    }
    mockSynthesizeFromRecording.mockResolvedValueOnce(mockResult)

    const { result } = renderHook(() => useRecordingWithSynthesis())

    await act(async () => {
      await result.current.startRecording()
    })

    await act(async () => {
      await result.current.stopRecording()
    })

    let synthesisResult
    await act(async () => {
      synthesisResult = await result.current.synthesizeFromRecording("Test task")
    })

    expect(synthesisResult).toEqual(mockResult)
  })

  it("should throw if synthesizing without recording", async () => {
    const { result } = renderHook(() => useRecordingWithSynthesis())

    await expect(
      act(async () => {
        await result.current.synthesizeFromRecording("Test task")
      })
    ).rejects.toThrow("No recording available")
  })
})
