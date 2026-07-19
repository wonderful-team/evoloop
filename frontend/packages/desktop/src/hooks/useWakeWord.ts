import { invoke } from "@tauri-apps/api/core"
import { listen } from "@tauri-apps/api/event"
import { useCallback, useEffect, useRef, useState } from "react"
import { isTauri } from "@/lib/tauri"

interface UseWakeWordOptions {
  wakeWord?: string
  onWake?: () => void
  enabled?: boolean
}

interface UseWakeWordReturn {
  isListening: boolean
  isWakeWordDetected: boolean
  error: string | null
  startListening: () => void
  stopListening: () => void
  transcript: string
}

export function useWakeWord(
  options: UseWakeWordOptions = {},
): UseWakeWordReturn {
  const {
    wakeWord = "你好 Evo",
    onWake,
  } = options

  const [isListening, setIsListening] = useState(false)
  const [isWakeWordDetected, setIsWakeWordDetected] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [transcript, setTranscript] = useState("")
  const unlistenRef = useRef<(() => void) | null>(null)
  const timeoutRef = useRef<NodeJS.Timeout | null>(null)

  // Listen for wake-word-detected Tauri event
  useEffect(() => {
    if (!isTauri()) {
      setError("Wake word requires the desktop app")
      return
    }

    const setup = async () => {
      const unlisten = await listen<{ word: string; transcript: string }>(
        "wake-word-detected",
        (event) => {
          setTranscript(event.payload.transcript)
          setIsWakeWordDetected(true)
          onWake?.()

          if (timeoutRef.current) clearTimeout(timeoutRef.current)
          timeoutRef.current = setTimeout(() => {
            setIsWakeWordDetected(false)
            setTranscript("")
          }, 3000)
        },
      )
      unlistenRef.current = unlisten
    }
    setup()

    return () => {
      unlistenRef.current?.()
      if (timeoutRef.current) clearTimeout(timeoutRef.current)
    }
  }, [onWake])

  const startListening = useCallback(async () => {
    if (!isTauri()) return
    try {
      await invoke("start_wake_word_listener", { word: wakeWord })
      setIsListening(true)
      setError(null)
    } catch (e: any) {
      setError(e.message || String(e))
      setIsListening(false)
    }
  }, [wakeWord])

  const stopListening = useCallback(async () => {
    if (!isTauri()) return
    try {
      await invoke("stop_wake_word_listener")
    } catch {
      // ignore
    }
    setIsListening(false)
    setIsWakeWordDetected(false)
    if (timeoutRef.current) clearTimeout(timeoutRef.current)
  }, [])

  return {
    isListening,
    isWakeWordDetected,
    error,
    startListening,
    stopListening,
    transcript,
  }
}

export function useWakeWordSettings() {
  const [wakeWord, setWakeWord] = useState(() => {
    if (typeof window !== "undefined") {
      return localStorage.getItem("evoloop_wake_word") || "你好 Evo"
    }
    return "你好 Evo"
  })

  const [wakeWordEnabled, setWakeWordEnabled] = useState(false)

  const updateWakeWord = useCallback((newWord: string) => {
    setWakeWord(newWord)
    localStorage.setItem("evoloop_wake_word", newWord)
  }, [])

  const toggleWakeWord = useCallback(() => {
    setWakeWordEnabled((prev) => {
      const newValue = !prev
      localStorage.setItem("evoloop_wake_word_enabled", newValue.toString())
      return newValue
    })
  }, [])

  return {
    wakeWord,
    wakeWordEnabled,
    updateWakeWord,
    toggleWakeWord,
  }
}
