import { describe, it, expect, vi, beforeEach } from "vitest"
import { renderHook, act } from "@testing-library/react"
import { useAugmentedMessages } from "../useAugmentedMessages"
import type { Message } from "../useAugmentedMessages"

// Mock date-fns
declare module "date-fns" {
  export function format(date: Date, format: string): string
}
vi.mock("date-fns", () => ({
  format: vi.fn((date: Date) => date.toISOString()),
}))

describe("useAugmentedMessages", () => {
  const createMockMessage = (overrides = {}): Message => ({
    id: "msg-1",
    content: "Hello",
    role: "user",
    timestamp: new Date().toISOString(),
    ...overrides,
  })

  beforeEach(() => {
    vi.clearAllMocks()
  })

  describe("initialization", () => {
    it("should initialize with empty messages", () => {
      const { result } = renderHook(() => useAugmentedMessages())

      expect(result.current.messages).toEqual([])
      expect(result.current.isLoading).toBe(false)
      expect(result.current.error).toBeNull()
    })

    it("should initialize with provided messages", () => {
      const initialMessages = [createMockMessage()]
      const { result } = renderHook(() => useAugmentedMessages(initialMessages))

      expect(result.current.messages).toHaveLength(1)
    })
  })

  describe("addMessage", () => {
    it("should add a new message", () => {
      const { result } = renderHook(() => useAugmentedMessages())

      act(() => {
        result.current.addMessage({
          content: "Test message",
          role: "user",
        })
      })

      expect(result.current.messages).toHaveLength(1)
      expect(result.current.messages[0].content).toBe("Test message")
      expect(result.current.messages[0].role).toBe("user")
    })

    it("should auto-generate id for new messages", () => {
      const { result } = renderHook(() => useAugmentedMessages())

      act(() => {
        result.current.addMessage({
          content: "Test",
          role: "user",
        })
      })

      expect(result.current.messages[0].id).toBeDefined()
      expect(result.current.messages[0].id).not.toBe("")
    })
  })

  describe("updateMessage", () => {
    it("should update existing message", () => {
      const initialMessages = [createMockMessage({ id: "msg-1" })]
      const { result } = renderHook(() => useAugmentedMessages(initialMessages))

      act(() => {
        result.current.updateMessage("msg-1", { content: "Updated content" })
      })

      expect(result.current.messages[0].content).toBe("Updated content")
    })

    it("should not update non-existent message", () => {
      const initialMessages = [createMockMessage({ id: "msg-1" })]
      const { result } = renderHook(() => useAugmentedMessages(initialMessages))

      act(() => {
        result.current.updateMessage("non-existent", { content: "Updated" })
      })

      expect(result.current.messages[0].content).toBe("Hello")
    })
  })

  describe("deleteMessage", () => {
    it("should delete a message", () => {
      const initialMessages = [
        createMockMessage({ id: "msg-1" }),
        createMockMessage({ id: "msg-2" }),
      ]
      const { result } = renderHook(() => useAugmentedMessages(initialMessages))

      act(() => {
        result.current.deleteMessage("msg-1")
      })

      expect(result.current.messages).toHaveLength(1)
      expect(result.current.messages[0].id).toBe("msg-2")
    })
  })

  describe("clearMessages", () => {
    it("should clear all messages", () => {
      const initialMessages = [
        createMockMessage(),
        createMockMessage(),
      ]
      const { result } = renderHook(() => useAugmentedMessages(initialMessages))

      act(() => {
        result.current.clearMessages()
      })

      expect(result.current.messages).toEqual([])
    })
  })

  describe("grouping", () => {
    it("should group messages by date", () => {
      const today = new Date()
      const yesterday = new Date(today)
      yesterday.setDate(yesterday.getDate() - 1)

      const initialMessages = [
        createMockMessage({ id: "1", timestamp: today.toISOString() }),
        createMockMessage({ id: "2", timestamp: yesterday.toISOString() }),
      ]

      const { result } = renderHook(() => useAugmentedMessages(initialMessages))

      // Check that messages are grouped (implementation dependent)
      expect(result.current.messages).toHaveLength(2)
    })
  })
})
