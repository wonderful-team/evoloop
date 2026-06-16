import type { UnlistenFn } from "@tauri-apps/api/event"
import { useCallback, useEffect, useRef, useState } from "react"
import { isTauri, safeInvoke, safeListen } from "@/lib/tauri"

type TriggerMode = "longPress" | "doubleClick"

interface UseTauriVoiceShortcutOptions {
  onShortcutStart?: () => void
  onShortcutEnd?: () => void
  enabled?: boolean
}

interface UseTauriVoiceShortcutReturn {
  isListening: boolean
  isRecording: boolean
  error: string | null
  startListening: () => Promise<void>
  stopListening: () => Promise<void>
  setShortcutKey: (key: string) => Promise<void>
  setShortcutDuration: (durationMs: number) => Promise<void>
  setTriggerMode: (mode: TriggerMode) => Promise<void>
  setDoubleClickInterval: (intervalMs: number) => Promise<void>
}

export function useTauriVoiceShortcut(
  options: UseTauriVoiceShortcutOptions = {},
): UseTauriVoiceShortcutReturn {
  const { onShortcutStart, onShortcutEnd, enabled = true } = options

  const [isListening, setIsListening] = useState(false)
  const [isRecording, setIsRecording] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const unlistenStartRef = useRef<UnlistenFn | null>(null)
  const unlistenEndRef = useRef<UnlistenFn | null>(null)

  // Listen for Tauri events
  useEffect(() => {
    if (!enabled) return

    const setupListeners = async () => {
      if (!isTauri()) return
      try {
        unlistenStartRef.current = await safeListen(
          "voice-shortcut-start",
          () => {
            setIsRecording(true)
            onShortcutStart?.()
          },
        )

        unlistenEndRef.current = await safeListen("voice-shortcut-end", () => {
          setIsRecording(false)
          onShortcutEnd?.()
        })
      } catch (e) {
        console.error("Failed to setup voice shortcut listeners:", e)
        setError("Failed to setup shortcut listeners")
      }
    }

    setupListeners()

    return () => {
      unlistenStartRef.current?.()
      unlistenEndRef.current?.()
    }
  }, [enabled, onShortcutStart, onShortcutEnd])

  const startListening = useCallback(async () => {
    try {
      setError(null)
      await safeInvoke("start_voice_shortcut_listener")
      setIsListening(true)
    } catch (e) {
      console.error("Failed to start voice shortcut listener:", e)
      setError("Failed to start shortcut listener")
      throw e
    }
  }, [])

  const stopListening = useCallback(async () => {
    try {
      await safeInvoke("stop_voice_shortcut_listener")
      setIsListening(false)
      setIsRecording(false)
    } catch (e) {
      console.error("Failed to stop voice shortcut listener:", e)
      setError("Failed to stop shortcut listener")
    }
  }, [])

  const setShortcutKey = useCallback(async (key: string) => {
    try {
      await safeInvoke("set_voice_shortcut_key", { key })
    } catch (e) {
      console.error("Failed to set shortcut key:", e)
      setError("Failed to set shortcut key")
    }
  }, [])

  const setShortcutDuration = useCallback(async (durationMs: number) => {
    try {
      await safeInvoke("set_voice_shortcut_duration", { durationMs })
    } catch (e) {
      console.error("Failed to set shortcut duration:", e)
      setError("Failed to set shortcut duration")
    }
  }, [])

  const setTriggerMode = useCallback(async (mode: TriggerMode) => {
    try {
      await safeInvoke("set_voice_shortcut_mode", { mode })
    } catch (e) {
      console.error("Failed to set trigger mode:", e)
      setError("Failed to set trigger mode")
    }
  }, [])

  const setDoubleClickInterval = useCallback(async (intervalMs: number) => {
    try {
      await safeInvoke("set_voice_shortcut_interval", { intervalMs })
    } catch (e) {
      console.error("Failed to set double click interval:", e)
      setError("Failed to set double click interval")
    }
  }, [])

  return {
    isListening,
    isRecording,
    error,
    startListening,
    stopListening,
    setShortcutKey,
    setShortcutDuration,
    setTriggerMode,
    setDoubleClickInterval,
  }
}

// Settings hook with localStorage persistence
export function useTauriVoiceShortcutSettings() {
  const [shortcutKey, setShortcutKeyState] = useState(() => {
    if (typeof window !== "undefined") {
      return localStorage.getItem("evoloop_voice_shortcut_key") || "Ctrl"
    }
    return "Ctrl"
  })

  const [triggerMode, setTriggerModeState] = useState<TriggerMode>(() => {
    if (typeof window !== "undefined") {
      return (
        (localStorage.getItem("evoloop_voice_trigger_mode") as TriggerMode) ||
        "doubleClick"
      )
    }
    return "doubleClick"
  })

  const [doubleClickInterval, setDoubleClickIntervalState] = useState(() => {
    if (typeof window !== "undefined") {
      return parseInt(
        localStorage.getItem("evoloop_voice_double_click_interval") || "300",
        10,
      )
    }
    return 300
  })

  const [shortcutDuration, setShortcutDurationState] = useState(() => {
    if (typeof window !== "undefined") {
      return parseInt(
        localStorage.getItem("evoloop_voice_shortcut_duration") || "500",
        10,
      )
    }
    return 500
  })

  const [shortcutEnabled, setShortcutEnabled] = useState(() => {
    if (typeof window !== "undefined") {
      return localStorage.getItem("evoloop_voice_shortcut_enabled") === "true"
    }
    return false
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

  const updateTriggerMode = useCallback(async (mode: TriggerMode) => {
    setTriggerModeState(mode)
    localStorage.setItem("evoloop_voice_trigger_mode", mode)
    try {
      await safeInvoke("set_voice_shortcut_mode", { mode })
    } catch (e) {
      console.error("Failed to update trigger mode:", e)
    }
  }, [])

  const updateDoubleClickInterval = useCallback(async (interval: number) => {
    setDoubleClickIntervalState(interval)
    localStorage.setItem(
      "evoloop_voice_double_click_interval",
      interval.toString(),
    )
    try {
      await safeInvoke("set_voice_shortcut_interval", { intervalMs: interval })
    } catch (e) {
      console.error("Failed to update double click interval:", e)
    }
  }, [])

  const updateShortcutDuration = useCallback(async (duration: number) => {
    setShortcutDurationState(duration)
    localStorage.setItem("evoloop_voice_shortcut_duration", duration.toString())
    try {
      await safeInvoke("set_voice_shortcut_duration", { durationMs: duration })
    } catch (e) {
      console.error("Failed to update shortcut duration:", e)
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
    // Apply saved settings
    safeInvoke("set_voice_shortcut_key", { key: shortcutKey }).catch(
      console.error,
    )
    safeInvoke("set_voice_shortcut_mode", { mode: triggerMode }).catch(
      console.error,
    )
    safeInvoke("set_voice_shortcut_interval", {
      intervalMs: doubleClickInterval,
    }).catch(console.error)
    safeInvoke("set_voice_shortcut_duration", {
      durationMs: shortcutDuration,
    }).catch(console.error)
    safeInvoke("start_voice_shortcut_listener").catch(console.error)
  }, []) // Only run once on mount

  return {
    shortcutKey,
    triggerMode,
    doubleClickInterval,
    shortcutDuration,
    shortcutEnabled,
    updateShortcutKey,
    updateTriggerMode,
    updateDoubleClickInterval,
    updateShortcutDuration,
    toggleShortcut,
  }
}
