import { describe, it, expect } from "vitest"
import { renderHook } from "@testing-library/react"
import { useIsMobile } from "../useMobile"

describe("useMobile", () => {
  it("should return false for desktop viewport", () => {
    window.matchMedia = vi.fn().mockImplementation((query: string) => ({
      matches: false,
      media: query,
      onchange: null,
      addListener: vi.fn(),
      removeListener: vi.fn(),
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
      dispatchEvent: vi.fn(),
    }))

    const { result } = renderHook(() => useIsMobile())
    expect(result.current).toBe(false)
  })

  it("should return true for mobile viewport", () => {
    window.matchMedia = vi.fn().mockImplementation((query: string) => ({
      matches: query === "(max-width: 768px)",
      media: query,
      onchange: null,
      addListener: vi.fn(),
      removeListener: vi.fn(),
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
      dispatchEvent: vi.fn(),
    }))

    const { result } = renderHook(() => useIsMobile())
    expect(result.current).toBe(true)
  })

  it("should update when media query changes", () => {
    let matches = false
    const listeners: Array<() => void> = []

    window.matchMedia = vi.fn().mockImplementation((query: string) => ({
      get matches() {
        return matches
      },
      media: query,
      onchange: null,
      addListener: vi.fn(),
      removeListener: vi.fn(),
      addEventListener: vi.fn((_, listener: () => void) => {
        listeners.push(listener)
      }),
      removeEventListener: vi.fn((_, listener: () => void) => {
        const index = listeners.indexOf(listener)
        if (index > -1) listeners.splice(index, 1)
      }),
      dispatchEvent: vi.fn(),
    }))

    const { result, rerender } = renderHook(() => useIsMobile())
    expect(result.current).toBe(false)

    // Simulate media query change
    matches = true
    listeners.forEach((listener) => listener())
    rerender()

    expect(result.current).toBe(true)
  })
})
