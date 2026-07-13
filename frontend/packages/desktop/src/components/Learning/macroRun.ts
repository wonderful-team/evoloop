/**
 * Macro run step feed — pure state helpers for the macro_thought stream.
 *
 * The backend MacroEngine emits one `macro_thought` system_log event per
 * executed step ({ text }); ChatConnection forwards them to the agent store,
 * which keeps a capped rolling feed per run. The component MacroRunFeed
 * renders whatever the store holds.
 */

export interface MacroStepEntry {
  text: string
  ts: number
}

export const MACRO_FEED_LIMIT = 50

/** Append a step, keeping only the newest MACRO_FEED_LIMIT entries. */
export function appendMacroStep(
  steps: MacroStepEntry[],
  text: string,
  ts: number,
  limit: number = MACRO_FEED_LIMIT,
): MacroStepEntry[] {
  if (!text) return steps
  const next = [...steps, { text, ts }]
  return next.length > limit ? next.slice(next.length - limit) : next
}

/** Extract the step text from a raw system_log payload; null if unusable. */
export function macroThoughtText(payload: unknown): string | null {
  const data = (payload as { data?: unknown } | undefined)?.data ?? payload
  const text = (data as { text?: unknown } | undefined)?.text
  return typeof text === "string" && text.length > 0 ? text : null
}
