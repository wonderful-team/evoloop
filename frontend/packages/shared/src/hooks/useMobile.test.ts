import { act, renderHook } from "@testing-library/react"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
import { useIsMobile } from "./useMobile"

describe("useIsMobile hook", () => {
  let listeners: Array<() => void> = []

  beforeEach(() => {
    listeners = []
    Object.defineProperty(window, "matchMedia", {
      writable: true,
      value: vi.fn().mockImplementation((query: string) => ({
        matches: false,
        media: query,
        onchange: null,
        addListener: vi.fn(),
        removeListener: vi.fn(),
        addEventListener: vi.fn((event: string, callback: () => void) => {
          if (event === "change") listeners.push(callback)
        }),
        removeEventListener: vi.fn((_event: string, callback: () => void) => {
          listeners = listeners.filter((l) => l !== callback)
        }),
        dispatchEvent: vi.fn(),
      })),
    })
  })

  afterEach(() => {
    listeners = []
  })

  it("returns true when innerWidth is below 768", () => {
    window.innerWidth = 500
    const { result } = renderHook(() => useIsMobile())
    expect(result.current).toBe(true)
  })

  it("returns false when innerWidth is at or above 768", () => {
    window.innerWidth = 1024
    const { result } = renderHook(() => useIsMobile())
    expect(result.current).toBe(false)
  })

  it("updates when media query change event fires", () => {
    window.innerWidth = 1024
    const { result } = renderHook(() => useIsMobile())
    expect(result.current).toBe(false)

    act(() => {
      window.innerWidth = 600
      listeners.forEach((fn) => fn())
    })

    expect(result.current).toBe(true)
  })
})
