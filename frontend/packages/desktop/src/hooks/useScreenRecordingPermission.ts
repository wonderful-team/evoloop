import { useState, useCallback, useEffect } from "react"
import { invoke } from "@tauri-apps/api/core"

export function useScreenRecordingPermission() {
    const [hasPermission, setHasPermission] = useState<boolean | null>(null)

    const checkPermission = useCallback(async () => {
        try {
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
    }, [])

    const requestPermission = useCallback(async () => {
        if (!window.__TAURI__) return
        try {
            await invoke("open_screen_recording_settings")
            // Re-check immediately
            await checkPermission()
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
