import { useState, useCallback, useEffect, useRef } from "react"
import { safeInvoke, isTauri } from "@/lib/tauri"

// Throttle interval: 10 seconds between permission checks (reduced from 30s)
const CHECK_THROTTLE_MS = 10000
// Debounce focus events to avoid rapid re-checks
const FOCUS_DEBOUNCE_MS = 500

export function useScreenRecordingPermission() {
    const [hasPermission, setHasPermission] = useState<boolean | null>(null)
    const [isChecking, setIsChecking] = useState(false)
    const lastCheckTime = useRef<number>(0)
    const focusTimeoutRef = useRef<number | null>(null)
    // Track consecutive failures to avoid flickering UI
    const consecutiveFalseCount = useRef<number>(0)

    const checkPermission = useCallback(async (force = false) => {
        // Prevent concurrent checks
        if (isChecking && !force) {
            console.log("[useScreenRecordingPermission] Skipping check (already in progress)")
            return hasPermission ?? true
        }

        // Skip Tauri-only permission checks in web mode
        if (!isTauri()) {
            setHasPermission(true)
            return true
        }

        // Throttle checks unless forced
        const now = Date.now()
        if (!force && now - lastCheckTime.current < CHECK_THROTTLE_MS) {
            console.log("[useScreenRecordingPermission] Skipping check (throttled)")
            return hasPermission ?? true
        }

        setIsChecking(true)
        try {
            lastCheckTime.current = now
            const result = await safeInvoke<boolean>("check_screen_recording_permission")
            console.log("[useScreenRecordingPermission] checkPermission result:", result)

            // Only update state if result is stable or forced
            // If we had permission before and now it's false, require 2 consecutive failures
            if (hasPermission === true && result === false && !force) {
                consecutiveFalseCount.current += 1
                if (consecutiveFalseCount.current < 2) {
                    console.log("[useScreenRecordingPermission] Ignoring single false result, waiting for confirmation")
                    setIsChecking(false)
                    return hasPermission ?? true
                }
            } else {
                consecutiveFalseCount.current = 0
            }

            setHasPermission(result)
            return result
        } catch (error) {
            console.warn("Check screen recording permission failed:", error)
            // Default to previous value or true to avoid flickering
            const fallback = hasPermission ?? true
            setHasPermission(fallback)
            return fallback
        } finally {
            setIsChecking(false)
        }
    }, [hasPermission, isChecking])

    const requestPermission = useCallback(async () => {
        if (!isTauri()) return
        try {
            await safeInvoke("open_screen_recording_settings")
            // Reset failure count when user opens settings
            consecutiveFalseCount.current = 0
            // Re-check after a delay (user needs time to grant permission)
            setTimeout(() => checkPermission(true), 1000)
        } catch (error) {
            console.error("Failed to open screen recording settings:", error)
        }
    }, [checkPermission])

    useEffect(() => {
        const onFocus = () => {
            // Debounce focus events
            if (focusTimeoutRef.current) {
                window.clearTimeout(focusTimeoutRef.current)
            }
            focusTimeoutRef.current = window.setTimeout(() => {
                // Only re-check if we don't already have permission confirmed
                if (hasPermission !== true) {
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
    }, [checkPermission, hasPermission])

    return { hasPermission, checkPermission, requestPermission }
}
