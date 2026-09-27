import { describe, expect, it } from "vitest"
import { fmtDuration } from "./fmt"

describe("fmtDuration utility", () => {
  it("returns dash when fromIso is null or empty", () => {
    expect(fmtDuration(null)).toBe("—")
    expect(fmtDuration("")).toBe("—")
  })

  it("returns 0m when diff is zero or negative", () => {
    const now = 1700000000000
    const future = new Date(now + 10000).toISOString()
    expect(fmtDuration(future, now)).toBe("0m")
  })

  it("formats minutes and seconds when under 60 minutes", () => {
    const now = 1700000000000
    // 5 minutes and 23 seconds ago
    const past = new Date(now - (5 * 60 * 1000 + 23 * 1000)).toISOString()
    expect(fmtDuration(past, now)).toBe("5m 23s")
  })

  it("formats hours and minutes when over 60 minutes", () => {
    const now = 1700000000000
    // 2 hours and 8 minutes ago
    const past = new Date(now - (2 * 3600 * 1000 + 8 * 60 * 1000)).toISOString()
    expect(fmtDuration(past, now)).toBe("2h 08m")
  })
})
