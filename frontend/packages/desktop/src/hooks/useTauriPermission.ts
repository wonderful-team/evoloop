import { useCallback, useEffect, useRef, useState } from "react"
import { isTauri, safeInvoke } from "@/lib/tauri"

// Throttle interval: 10 seconds between permission checks
const CHECK_THROTTLE_MS = 10000
// Debounce focus events to avoid rapid re-checks
const FOCUS_DEBOUNCE_MS = 500

// Module-level state shared across all hook instances so that multiple
// components (e.g. RecordingButton + GlobalRecorderManager) do not all fire
// permission probes at the same time on mount or after a WebView reload.
let globalLastCheckTime = 0
let globalIsChecking = false
let globalLastResult: boolean | null = null

export interface UseTauriPermissionOptions {
  checkCommand: string
  openSettingsCommand: string
  label?: string
}

export function useTauriPermission({
  checkCommand,
  openSettingsCommand,
  label = "Permission",
}: UseTauriPermissionOptions) {
  const [hasPermission, setHasPermission] = useState<boolean | null>(null)
  const [isChecking, setIsChecking] = useState(false)
  const focusTimeoutRef = useRef<number | null>(null)
  // Track consecutive failures to avoid flickering UI
  const consecutiveFalseCount = useRef<number>(0)

  // Use refs for values read inside checkPermission so the callback identity
  // stays stable and does not re-trigger the mount/focus effects in a loop.
  const isCheckingRef = useRef(isChecking)
  const hasPermissionRef = useRef(hasPermission)
  useEffect(() => {
    isCheckingRef.current = isChecking
  }, [isChecking])
  useEffect(() => {
    hasPermissionRef.current = hasPermission
  }, [hasPermission])

  const checkPermission = useCallback(
    async (force = false) => {
      // Skip Tauri-only permission checks in web mode
      if (!isTauri()) {
        setHasPermission(true)
        return true
      }

      const now = Date.now()

      // Global throttle: any instance checked recently?
      if (!force && now - globalLastCheckTime < CHECK_THROTTLE_MS) {
        console.log(`[useTauriPermission:${label}] Skipping check (globally throttled)`)
        // Synchronize local state with the cached global result when available.
        if (globalLastResult !== null && hasPermissionRef.current !== globalLastResult) {
          setHasPermission(globalLastResult)
        }
        return globalLastResult ?? hasPermissionRef.current ?? true
      }

      // Prevent concurrent checks globally
      if (globalIsChecking && !force) {
        console.log(`[useTauriPermission:${label}] Skipping check (already in progress)`)
        return globalLastResult ?? hasPermissionRef.current ?? true
      }

      globalIsChecking = true
      setIsChecking(true)
      try {
        globalLastCheckTime = now
        const result = await safeInvoke<boolean>(checkCommand)
        globalLastResult = result
        console.log(`[useTauriPermission:${label}] checkPermission result:`, result)

        // Only update state if result is stable or forced
        // If we had permission before and now it's false, require 2 consecutive failures
        if (hasPermissionRef.current === true && result === false && !force) {
          consecutiveFalseCount.current += 1
          if (consecutiveFalseCount.current < 2) {
            console.log(
              `[useTauriPermission:${label}] Ignoring single false result, waiting for confirmation`,
            )
            return hasPermissionRef.current ?? true
          }
        } else {
          consecutiveFalseCount.current = 0
        }

        setHasPermission(result)
        return result
      } catch (error) {
        console.warn(`Check ${label} permission failed:`, error)
        const fallback = hasPermissionRef.current ?? true
        setHasPermission(fallback)
        return fallback
      } finally {
        globalIsChecking = false
        setIsChecking(false)
      }
    },
    [checkCommand, label],
  )

  const requestPermission = useCallback(async () => {
    if (!isTauri()) return
    try {
      await safeInvoke(openSettingsCommand)
      consecutiveFalseCount.current = 0
      setTimeout(() => checkPermission(true), 1000)
    } catch (error) {
      console.error(`Failed to open ${label} settings:`, error)
    }
  }, [checkPermission, label, openSettingsCommand])

  useEffect(() => {
    checkPermission(false)
  }, [checkPermission])

  useEffect(() => {
    const onFocus = () => {
      if (focusTimeoutRef.current) {
        window.clearTimeout(focusTimeoutRef.current)
      }
      focusTimeoutRef.current = window.setTimeout(() => {
        if (hasPermissionRef.current !== true) {
          checkPermission()
        }
      }, FOCUS_DEBOUNCE_MS)
    }

    window.addEventListener("focus", onFocus)
    return () => {
      window.removeEventListener("focus", onFocus)
      if (focusTimeoutRef.current) {
        window.clearTimeout(focusTimeoutRef.current)
      }
    }
  }, [checkPermission])

  return { hasPermission, checkPermission, requestPermission }
}
