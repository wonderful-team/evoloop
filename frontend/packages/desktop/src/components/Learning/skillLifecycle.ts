import { ApiError } from "@/client"

/**
 * Client-side mirror of the backend routable rule
 * (app/core/learning/skill_visibility.py: is_routable):
 * a skill may be executed only when it is active AND verified.
 * Keep in sync with the backend predicate — pinned by
 * skillLifecycle.test.ts.
 */
export function isSkillRoutable(skill: {
  is_active: boolean
  status?: string | null
}): boolean {
  return skill.is_active === true && skill.status === "verified"
}

/**
 * Actionable server message for execute_skill failures.
 * The backend gates execution of non-routable skills with 403 + a detail
 * string explaining the required confirmation; surface it instead of the
 * generic failure toast. Returns null for every other failure.
 */
export function executeSkillErrorMessage(error: unknown): string | null {
  if (error instanceof ApiError && error.status === 403) {
    const detail = (error.body as { detail?: unknown } | undefined)?.detail
    return typeof detail === "string" && detail.length > 0 ? detail : null
  }
  return null
}
