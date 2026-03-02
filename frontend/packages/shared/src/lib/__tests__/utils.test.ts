import { describe, it, expect } from "vitest"
import { cn } from "../utils"

describe("cn (className utility)", () => {
  it("should merge class names", () => {
    const result = cn("class1", "class2")
    expect(result).toBe("class1 class2")
  })

  it("should handle conditional classes", () => {
    const result = cn("class1", false && "class2", "class3")
    expect(result).toBe("class1 class3")
  })

  it("should handle undefined and null", () => {
    const result = cn("class1", undefined, null, "class2")
    expect(result).toBe("class1 class2")
  })

  it("should merge tailwind classes correctly", () => {
    const result = cn("px-2 py-1", "px-4")
    // tailwind-merge should resolve conflicts
    expect(result).toContain("px-4")
    expect(result).toContain("py-1")
  })

  it("should handle array of classes", () => {
    const result = cn(["class1", "class2"], "class3")
    expect(result).toBe("class1 class2 class3")
  })

  it("should handle object syntax", () => {
    const result = cn({ "class1": true, "class2": false, "class3": true })
    expect(result).toBe("class1 class3")
  })

  it("should handle nested arrays", () => {
    const result = cn("class1", ["class2", ["class3", "class4"]])
    expect(result).toBe("class1 class2 class3 class4")
  })

  it("should return empty string for no arguments", () => {
    const result = cn()
    expect(result).toBe("")
  })

  it("should handle complex combinations", () => {
    const isActive = true
    const isDisabled = false

    const result = cn(
      "base-class",
      isActive && "active",
      isDisabled && "disabled",
      ["array-class"],
      { "object-class": true }
    )

    expect(result).toContain("base-class")
    expect(result).toContain("active")
    expect(result).not.toContain("disabled")
    expect(result).toContain("array-class")
    expect(result).toContain("object-class")
  })
})
