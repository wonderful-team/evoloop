import { describe, it, expect, vi, beforeEach } from "vitest"
import { useRecordingStore } from "../recordingStore"

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

describe("useRecordingStore", () => {
  beforeEach(() => {
    // Reset store to initial state
    useRecordingStore.getState().reset()
    vi.clearAllMocks()
  })

  describe("initial state", () => {
    it("should have correct initial values", () => {
      const state = useRecordingStore.getState()

      expect(state.isRecording).toBe(false)
      expect(state.isGlobalMode).toBe(false)
      expect(state.activeThreadId).toBeNull()
      expect(state.eventCount).toBe(0)
      expect(state.sessionId).toBeNull()
      expect(state.videoPath).toBeNull()
      expect(state.postRecordingAction).toBeNull()
    })
  })

  describe("startRecording", () => {
    it("should start recording with threadId", () => {
      const { startRecording } = useRecordingStore.getState()

      startRecording("thread-123")

      const state = useRecordingStore.getState()
      expect(state.isRecording).toBe(true)
      expect(state.activeThreadId).toBe("thread-123")
      expect(state.eventCount).toBe(0)
      expect(state.sessionId).toBeNull()
      expect(state.videoPath).toBeNull()
    })

    it("should reset previous state when starting new recording", () => {
      const store = useRecordingStore.getState()

      // Set some initial state
      store.startRecording("thread-1")
      store.setEventCount(5)
      store.setSessionId("session-1")
      store.setVideoPath("/path/to/video")
      store.setPostRecordingAction("synthesize")

      // Start new recording
      store.startRecording("thread-2")

      const state = useRecordingStore.getState()
      expect(state.isRecording).toBe(true)
      expect(state.activeThreadId).toBe("thread-2")
      expect(state.eventCount).toBe(0)
      expect(state.sessionId).toBeNull()
      expect(state.videoPath).toBeNull()
      expect(state.postRecordingAction).toBeNull()
    })
  })

  describe("stopRecording", () => {
    it("should stop recording", () => {
      const store = useRecordingStore.getState()

      store.startRecording("thread-123")
      expect(useRecordingStore.getState().isRecording).toBe(true)

      store.stopRecording()

      const state = useRecordingStore.getState()
      expect(state.isRecording).toBe(false)
    })

    it("should keep activeThreadId after stop", () => {
      const store = useRecordingStore.getState()

      store.startRecording("thread-123")
      store.stopRecording()

      const state = useRecordingStore.getState()
      expect(state.activeThreadId).toBe("thread-123")
    })
  })

  describe("setEventCount", () => {
    it("should update event count", () => {
      const { setEventCount } = useRecordingStore.getState()

      setEventCount(10)

      expect(useRecordingStore.getState().eventCount).toBe(10)
    })

    it("should handle zero events", () => {
      const { setEventCount } = useRecordingStore.getState()

      setEventCount(0)

      expect(useRecordingStore.getState().eventCount).toBe(0)
    })
  })

  describe("setSessionId", () => {
    it("should set session id", () => {
      const { setSessionId } = useRecordingStore.getState()

      setSessionId("session-456")

      expect(useRecordingStore.getState().sessionId).toBe("session-456")
    })

    it("should clear session id with null", () => {
      const { setSessionId } = useRecordingStore.getState()

      setSessionId("session-456")
      setSessionId(null)

      expect(useRecordingStore.getState().sessionId).toBeNull()
    })
  })

  describe("setIsGlobalMode", () => {
    it("should toggle global mode", () => {
      const { setIsGlobalMode } = useRecordingStore.getState()

      setIsGlobalMode(true)
      expect(useRecordingStore.getState().isGlobalMode).toBe(true)

      setIsGlobalMode(false)
      expect(useRecordingStore.getState().isGlobalMode).toBe(false)
    })
  })

  describe("setVideoPath", () => {
    it("should set video path", () => {
      const { setVideoPath } = useRecordingStore.getState()

      setVideoPath("/recordings/video-123.mp4")

      expect(useRecordingStore.getState().videoPath).toBe("/recordings/video-123.mp4")
    })

    it("should clear video path with null", () => {
      const { setVideoPath } = useRecordingStore.getState()

      setVideoPath("/recordings/video.mp4")
      setVideoPath(null)

      expect(useRecordingStore.getState().videoPath).toBeNull()
    })
  })

  describe("setPostRecordingAction", () => {
    it("should set post recording action", () => {
      const { setPostRecordingAction } = useRecordingStore.getState()

      setPostRecordingAction("synthesize")

      expect(useRecordingStore.getState().postRecordingAction).toBe("synthesize")
    })

    it("should clear post recording action", () => {
      const { setPostRecordingAction } = useRecordingStore.getState()

      setPostRecordingAction("synthesize")
      setPostRecordingAction(null)

      expect(useRecordingStore.getState().postRecordingAction).toBeNull()
    })
  })

  describe("reset", () => {
    it("should reset all state to initial values", () => {
      const store = useRecordingStore.getState()

      // Set all state values
      store.startRecording("thread-123")
      store.setIsGlobalMode(true)
      store.setEventCount(10)
      store.setSessionId("session-1")
      store.setVideoPath("/path/to/video")
      store.setPostRecordingAction("synthesize")

      // Reset
      store.reset()

      const state = useRecordingStore.getState()
      expect(state.isRecording).toBe(false)
      expect(state.isGlobalMode).toBe(false)
      expect(state.activeThreadId).toBeNull()
      expect(state.eventCount).toBe(0)
      expect(state.sessionId).toBeNull()
      expect(state.videoPath).toBeNull()
      expect(state.postRecordingAction).toBeNull()
    })
  })
})
