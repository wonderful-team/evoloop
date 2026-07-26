import type { UnlistenFn } from "@tauri-apps/api/event"
import { useCallback, useEffect, useRef, useState } from "react"
import { useTranslation } from "react-i18next"
import { isTauri, safeInvoke, safeListen } from "@/lib/tauri"

interface UseTauriVoiceShortcutOptions {
  onPress?: () => void
  enabled?: boolean
}

interface UseTauriVoiceShortcutReturn {
  isListening: boolean
  error: string | null
  startListening: () => Promise<void>
  stopListening: () => Promise<void>
  setShortcutKey: (key: string) => Promise<void>
  setLongPressThreshold: (durationMs: number) => Promise<void>
}

export function useTauriVoiceShortcut(
  options: UseTauriVoiceShortcutOptions = {},
): UseTauriVoiceShortcutReturn {
  const { t } = useTranslation()
  const { onPress, enabled = true } = options

  const [isListening, setIsListening] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const unlistenRef = useRef<UnlistenFn | null>(null)

  useEffect(() => {
    if (!enabled) return

    const setupListeners = async () => {
      if (!isTauri()) return
      try {
        unlistenRef.current = await safeListen("voice-shortcut-press", () => {
          onPress?.()
        })
      } catch (e) {
        console.error("Failed to setup voice shortcut listeners:", e)
        setError(t("settings.voice.shortcutErrors.setupListeners"))
      }
    }

    setupListeners()

    return () => {
      unlistenRef.current?.()
    }
  }, [enabled, onPress, t])

  const startListening = useCallback(async () => {
    try {
      setError(null)
      await safeInvoke("start_voice_shortcut_listener")
      setIsListening(true)
    } catch (e) {
      console.error("Failed to start voice shortcut listener:", e)
      setError(t("settings.voice.shortcutErrors.startListener"))
      throw e
    }
  }, [t])

  const stopListening = useCallback(async () => {
    try {
      await safeInvoke("stop_voice_shortcut_listener")
      setIsListening(false)
    } catch (e) {
      console.error("Failed to stop voice shortcut listener:", e)
      setError(t("settings.voice.shortcutErrors.stopListener"))
    }
  }, [t])

  const setShortcutKey = useCallback(
    async (key: string) => {
      try {
        await safeInvoke("set_voice_shortcut_key", { key })
      } catch (e) {
        console.error("Failed to set shortcut key:", e)
        setError(t("settings.voice.shortcutErrors.setKey"))
      }
    },
    [t],
  )

  const setLongPressThreshold = useCallback(
    async (durationMs: number) => {
      try {
        await safeInvoke("set_voice_shortcut_duration", { durationMs })
      } catch (e) {
        console.error("Failed to set long press threshold:", e)
        setError(t("settings.voice.shortcutErrors.setDuration"))
      }
    },
    [t],
  )

  return {
    isListening,
    error,
    startListening,
    stopListening,
    setShortcutKey,
    setLongPressThreshold,
  }
}

// Settings hook with localStorage persistence
export function useTauriVoiceShortcutSettings() {
  const [shortcutKey, setShortcutKeyState] = useState(() => {
    if (typeof window !== "undefined") {
      const stored = localStorage.getItem("evoloop_voice_shortcut_key")
      if (stored && stored !== "F10" && stored !== "Alt+F12" && stored !== "F8" && stored !== "Alt+V") return stored
      return "Ctrl+Alt+V"
    }
    return "Ctrl+Alt+V"
  })

  const [longPressThreshold, setLongPressThresholdState] = useState(() => {
    if (typeof window !== "undefined") {
      return parseInt(
        localStorage.getItem("evoloop_voice_long_press_threshold") || "500",
        10,
      )
    }
    return 500
  })

  const [shortcutEnabled, setShortcutEnabled] = useState(() => {
    if (typeof window !== "undefined") {
      const stored = localStorage.getItem("evoloop_voice_shortcut_enabled")
      return stored === null ? true : stored === "true"
    }
    return true
  })

  const updateShortcutKey = useCallback(async (key: string) => {
    setShortcutKeyState(key)
    localStorage.setItem("evoloop_voice_shortcut_key", key)
    try {
      await safeInvoke("set_voice_shortcut_key", { key })
    } catch (e) {
      console.error("Failed to update shortcut key:", e)
    }
  }, [])

  const updateLongPressThreshold = useCallback(async (ms: number) => {
    setLongPressThresholdState(ms)
    localStorage.setItem("evoloop_voice_long_press_threshold", ms.toString())
    try {
      await safeInvoke("set_voice_shortcut_duration", { durationMs: ms })
    } catch (e) {
      console.error("Failed to update long press threshold:", e)
    }
  }, [])

  const toggleShortcut = useCallback(async () => {
    const newValue = !shortcutEnabled
    setShortcutEnabled(newValue)
    localStorage.setItem("evoloop_voice_shortcut_enabled", newValue.toString())

    try {
      if (newValue) {
        await safeInvoke("start_voice_shortcut_listener")
      } else {
        await safeInvoke("stop_voice_shortcut_listener")
      }
    } catch (e) {
      console.error("Failed to toggle shortcut:", e)
    }
  }, [shortcutEnabled])

  // Initialize shortcut settings on mount
  useEffect(() => {
    if (!isTauri() || !shortcutEnabled) return
    safeInvoke("set_voice_shortcut_key", { key: shortcutKey }).catch(
      console.error,
    )
    safeInvoke("set_voice_shortcut_duration", {
      durationMs: longPressThreshold,
    }).catch(console.error)
    safeInvoke("start_voice_shortcut_listener").catch(console.error)
  }, []) // Only run once on mount

  return {
    shortcutKey,
    longPressThreshold,
    shortcutEnabled,
    updateShortcutKey,
    updateLongPressThreshold,
    toggleShortcut,
  }
}
