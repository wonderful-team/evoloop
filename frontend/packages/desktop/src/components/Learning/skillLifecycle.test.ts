import { describe, expect, it } from "vitest"
import { ApiError } from "@/client"
import {
  executeSkillErrorMessage,
  isSkillRoutable,
} from "./skillLifecycle"

describe("skillLifecycle client rules", () => {
  describe("isSkillRoutable", () => {
    it("returns true only when is_active is true and status is verified", () => {
      expect(isSkillRoutable({ is_active: true, status: "verified" })).toBe(
        true,
      )

      expect(isSkillRoutable({ is_active: false, status: "verified" })).toBe(
        false,
      )
      expect(isSkillRoutable({ is_active: true, status: "draft" })).toBe(false)
      expect(isSkillRoutable({ is_active: true, status: "archived" })).toBe(
        false,
      )
      expect(isSkillRoutable({ is_active: true, status: null })).toBe(false)
      expect(isSkillRoutable({ is_active: true })).toBe(false)
    })
  })

  describe("executeSkillErrorMessage", () => {
    it("extracts 403 detail string from ApiError", () => {
      const err = new ApiError(
        { method: "POST", url: "/api/v1/skills/1/execute" },
        {
          status: 403,
          statusText: "Forbidden",
          body: { detail: "Skill must be verified before execution" },
          url: "/api/v1/skills/1/execute",
          ok: false,
        },
        "Forbidden",
      )

      expect(executeSkillErrorMessage(err)).toBe(
        "Skill must be verified before execution",
      )
    })

    it("returns null for non-403 or non-ApiError", () => {
      const err500 = new ApiError(
        { method: "POST", url: "/test" },
        {
          status: 500,
          statusText: "Internal Server Error",
          body: { detail: "Crash" },
          url: "/test",
          ok: false,
        },
        "Crash",
      )
      expect(executeSkillErrorMessage(err500)).toBeNull()
      expect(executeSkillErrorMessage(new Error("Generic"))).toBeNull()
      expect(executeSkillErrorMessage(null)).toBeNull()
    })
  })
})
