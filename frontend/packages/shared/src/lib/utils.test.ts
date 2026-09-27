import { describe, expect, it } from "vitest"
import { cn } from "./utils"

describe("cn utility", () => {
  it("merges class names correctly", () => {
    expect(cn("px-2", "py-1")).toBe("px-2 py-1")
  })

  it("handles conditional class names", () => {
    const isPrimary = true
    const isGhost = false
    expect(cn("btn", isPrimary && "btn-primary", isGhost && "btn-ghost")).toBe(
      "btn btn-primary",
    )
  })

  it("handles null, undefined, and boolean falsy values", () => {
    expect(cn("base", null, undefined, false, 0 && "hidden")).toBe("base")
  })

  it("resolves tailwind conflicts according to precedence", () => {
    expect(cn("px-2 py-1", "p-4")).toBe("p-4")
    expect(cn("text-red-500", "text-blue-500")).toBe("text-blue-500")
    expect(cn("bg-red-500 hover:bg-red-600", "bg-blue-500")).toBe(
      "hover:bg-red-600 bg-blue-500",
    )
  })

  it("supports object format classes", () => {
    expect(cn("base", { active: true, disabled: false })).toBe("base active")
  })

  it("supports array of classes", () => {
    expect(cn(["font-bold", "text-sm"], "uppercase")).toBe(
      "font-bold text-sm uppercase",
    )
  })
})
