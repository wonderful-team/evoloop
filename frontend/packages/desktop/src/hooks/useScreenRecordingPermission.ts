import { useState, useCallback, useEffect, useRef } from "react"
import { invoke } from "@tauri-apps/api/core"

// Throttle interval: 30 seconds between permission checks
const CHECK_THROTTLE_MS = 30000

export function useScreenRecordingPermission() {
    const [hasPermission, setHasPermission] = useState<boolean | null>(null)
    const lastCheckTime = useRef<number>(0)

    const checkPermission = useCallback(async (force = false) => {
        // Throttle checks unless forced
        const now = Date.now()
        if (!force && now - lastCheckTime.current < CHECK_THROTTLE_MS) {
            console.log("[useScreenRecordingPermission] Skipping check (throttled)")
            return hasPermission ?? true
        }

        try {
            lastCheckTime.current = now
            const result = await invoke<boolean>("check_screen_recording_permission")
            console.log("[useScreenRecordingPermission] checkPermission result:", result)
            setHasPermission(result)
            return result
        } catch (error) {
            console.warn("Check screen recording permission failed:", error)
            // Default to true for non-macOS or error cases to avoid blocking
            setHasPermission(true)
            return true
        }
    }, [hasPermission])

    const requestPermission = useCallback(async () => {
        if (!window.__TAURI__) return
        try {
            await invoke("open_screen_recording_settings")
            // Re-check immediately (forced)
            await checkPermission(true)
        } catch (error) {
            console.error("Failed to open screen recording settings:", error)
        }
    }, [checkPermission])

    useEffect(() => {
        checkPermission()

        const onFocus = () => {
            checkPermission()
        }

        window.addEventListener("focus", onFocus)
        return () => window.removeEventListener("focus", onFocus)
    }, [checkPermission])

    return { hasPermission, checkPermission, requestPermission }
}
