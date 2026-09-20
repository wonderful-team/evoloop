/** Shared time formatting for the duty workbench. */
export function fmtDuration(
  fromIso: string | null,
  now: number = Date.now(),
): string {
  if (!fromIso) return "—"
  const ms = now - new Date(fromIso).getTime()
  if (ms <= 0) return "0m"
  const m = Math.floor(ms / 60000)
  const sec = Math.floor((ms % 60000) / 1000)
  if (m < 60) return `${m}m ${String(sec).padStart(2, "0")}s`
  return `${Math.floor(m / 60)}h ${String(m % 60).padStart(2, "0")}m`
}
