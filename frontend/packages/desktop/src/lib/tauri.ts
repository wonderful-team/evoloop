/**
 * Tauri platform detection and safe API wrappers.
 *
 * In pure Web mode (non-Tauri), all Tauri APIs are unavailable.
 * Use `isTauri()` to guard Tauri-only code paths, and the safe
 * wrappers below to noop gracefully when running in a browser.
 */

/** Returns true when running inside a Tauri desktop shell. */
export function isTauri(): boolean {
  return (
    typeof window !== "undefined" &&
    (!!(window as any).__TAURI_INTERNALS__ || !!(window as any).__TAURI__)
  )
}

/** Safe wrapper around @tauri-apps/api/event `listen`. */
export async function safeListen<T>(
  event: string,
  handler: (event: { payload: T }) => void,
): Promise<() => void> {
  if (!isTauri()) {
    return () => {}
  }
  const { listen } = await import("@tauri-apps/api/event")
  return listen(event, handler as any)
}

/** Safe wrapper around @tauri-apps/api/event `emit`. */
export async function safeEmit(
  event: string,
  payload?: unknown,
): Promise<void> {
  if (!isTauri()) {
    return
  }
  const { emit } = await import("@tauri-apps/api/event")
  return emit(event, payload)
}

/** Safe wrapper around @tauri-apps/api/core `invoke`. */
export async function safeInvoke<T>(
  cmd: string,
  args?: Record<string, unknown>,
): Promise<T> {
  if (!isTauri()) {
    throw new Error(`Tauri command "${cmd}" is not available in web mode`)
  }
  const { invoke } = await import("@tauri-apps/api/core")
  return invoke(cmd, args) as Promise<T>
}

/** Safe wrapper around @tauri-apps/api/window `getCurrentWindow`. */
export async function safeGetCurrentWindow() {
  if (!isTauri()) {
    return null
  }
  const { getCurrentWindow } = await import("@tauri-apps/api/window")
  return getCurrentWindow()
}
