import { useState, useCallback, useEffect } from "react"
import { invoke } from "@tauri-apps/api/core"

export function useAccessibilityPermission() {
    const [hasPermission, setHasPermission] = useState<boolean | null>(null)

    const checkPermission = useCallback(async () => {
        // Only relevant on macOS, but we can check checking OS or just catch error
        // Rust command is #[cfg(target_os = "macos")] so it might fail on windows if not handled
        try {
            // We can check platform first if needed, but let's assume invoke returns safely or we use try/catch
            const result = await invoke<boolean>("check_accessibility_permission")
            setHasPermission(result)
            return result
        } catch (error) {
            // Likely not implemented on this OS or other error
            // Treat as true for non-macOS or handle gracefully
            console.warn("Check permission failed (likely not in Tauri or not macOS):", error)
            // If checking fails, we might assume true to avoid blocking in browser dev
            setHasPermission(true)
            return true
        }
    }, [])

    const requestPermission = useCallback(async () => {
        if (!window.__TAURI__) return
        try {
            await invoke("open_accessibility_settings")

            // Re-check immediately after requesting. 
            // The prompt might block execution or return promptly. 
            // For good measure we might want to poll, but let's try a simple re-check first.
            await checkPermission()
        } catch (error) {
            console.error("Failed to open accessibility settings:", error)
        }
    }, [checkPermission])

    // Check on mount and focus
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
