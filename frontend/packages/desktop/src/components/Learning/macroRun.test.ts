import { describe, expect, it } from "vitest"
import {
  appendMacroStep,
  type MacroStepEntry,
  macroThoughtText,
} from "./macroRun"

describe("macroRun pure state helpers", () => {
  it("extracts text from nested or flat payload", () => {
    expect(macroThoughtText({ data: { text: "Step 1: Click button" } })).toBe(
      "Step 1: Click button",
    )
    expect(macroThoughtText({ text: "Direct text" })).toBe("Direct text")
    expect(macroThoughtText(null)).toBeNull()
    expect(macroThoughtText({})).toBeNull()
    expect(macroThoughtText({ data: { text: "" } })).toBeNull()
  })

  it("appends steps up to the limit and slides the rolling window", () => {
    let steps: MacroStepEntry[] = []

    steps = appendMacroStep(steps, "First", 1000, 3)
    steps = appendMacroStep(steps, "Second", 2000, 3)
    steps = appendMacroStep(steps, "Third", 3000, 3)

    expect(steps.length).toBe(3)
    expect(steps[0].text).toBe("First")
    expect(steps[2].text).toBe("Third")

    // Adding 4th step with limit 3 drops "First"
    steps = appendMacroStep(steps, "Fourth", 4000, 3)
    expect(steps.length).toBe(3)
    expect(steps.map((s) => s.text)).toEqual(["Second", "Third", "Fourth"])
  })

  it("ignores empty text when appending", () => {
    const original: MacroStepEntry[] = [{ text: "Existing", ts: 100 }]
    const result = appendMacroStep(original, "", 200)
    expect(result).toBe(original)
  })
})
