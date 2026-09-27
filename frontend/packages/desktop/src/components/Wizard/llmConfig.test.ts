import {describe, expect, it} from "vitest"

import {needsLlmStepForConfig} from "./llmConfig"

describe("needsLlmStepForConfig", () => {
  it("returns false for platform mode with no LLM_MODEL", () => {
    expect(needsLlmStepForConfig({ LLM_CONFIG_TYPE: "platform" })).toBe(false)
  })

  it("returns false for platform mode even with a stale LLM_MODEL", () => {
    expect(
      needsLlmStepForConfig({
        LLM_CONFIG_TYPE: "platform",
        LLM_MODEL: "deepseek-v4-flash",
      }),
    ).toBe(false)
  })

  it("defaults to platform mode when LLM_CONFIG_TYPE is absent", () => {
    expect(needsLlmStepForConfig({})).toBe(false)
    expect(needsLlmStepForConfig({ LLM_MODEL: "x" })).toBe(false)
  })

  it("returns true for custom mode without a model", () => {
    expect(
      needsLlmStepForConfig({
        LLM_CONFIG_TYPE: "custom",
        LLM_BASE_URL: "https://api.openai.com",
      }),
    ).toBe(true)
  })

  it("returns true for custom mode without a base URL", () => {
    expect(
      needsLlmStepForConfig({
        LLM_CONFIG_TYPE: "custom",
        LLM_MODEL: "gpt-4o",
      }),
    ).toBe(true)
  })

  it("returns true for custom mode with an empty model string", () => {
    expect(
      needsLlmStepForConfig({
        LLM_CONFIG_TYPE: "custom",
        LLM_MODEL: "",
        LLM_BASE_URL: "https://api.openai.com",
      }),
    ).toBe(true)
  })

  it("returns true for custom mode with an empty base URL", () => {
    expect(
      needsLlmStepForConfig({
        LLM_CONFIG_TYPE: "custom",
        LLM_MODEL: "gpt-4o",
        LLM_BASE_URL: "",
      }),
    ).toBe(true)
  })

  it("returns false for a complete custom config", () => {
    expect(
      needsLlmStepForConfig({
        LLM_CONFIG_TYPE: "custom",
        LLM_MODEL: "gpt-4o",
        LLM_BASE_URL: "https://api.openai.com",
      }),
    ).toBe(false)
  })
})
