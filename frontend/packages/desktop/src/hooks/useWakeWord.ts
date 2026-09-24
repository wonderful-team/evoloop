import {invoke} from "@tauri-apps/api/core"
import {listen} from "@tauri-apps/api/event"
import {useCallback, useEffect, useRef, useState} from "react"
import {isTauri} from "@/lib/tauri"

interface UseWakeWordOptions {
  wakeWord?: string
  onWake?: (word: string) => void
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
  const { wakeWord = "木头人", onWake } = options

  const [isListening, setIsListening] = useState(false)
  const [isWakeWordDetected, setIsWakeWordDetected] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [transcript, setTranscript] = useState("")
  const unlistenRef = useRef<(() => void) | null>(null)
  const errorUnlistenRef = useRef<(() => void) | null>(null)
  const timeoutRef = useRef<NodeJS.Timeout | null>(null)

  useEffect(() => {
    if (!isTauri()) return

    const setup = async () => {
      const unlisten = await listen<{ word: string; reply?: string }>(
        "wake-word-detected",
        (event) => {
          const word = event.payload.word || wakeWord
          setTranscript(word)
          setIsWakeWordDetected(true)
          onWake?.(word)
          if (timeoutRef.current) clearTimeout(timeoutRef.current)
          timeoutRef.current = setTimeout(() => {
            setIsWakeWordDetected(false)
            setTranscript("")
          }, 3000)
        },
      )
      unlistenRef.current = unlisten

      const unlistenError = await listen<{ code: string; message: string }>(
        "wake:error",
        (event) => {
          setError(event.payload.message)
          setIsListening(false)
        },
      )
      errorUnlistenRef.current = unlistenError
    }
    setup()

    return () => {
      unlistenRef.current?.()
      errorUnlistenRef.current?.()
      if (timeoutRef.current) clearTimeout(timeoutRef.current)
    }
  }, [onWake, wakeWord])

  // Start detector on mount if enabled in localStorage
  useEffect(() => {
    if (!isTauri()) return
    let cancelled = false
    ;(async () => {
      const isEnabled = localStorage.getItem("evoloop_wake_word_enabled") === "true"
      if (!isEnabled) return
      const word = localStorage.getItem("evoloop_wake_word") || localStorage.getItem("evoloop_device_name") || "木头人"
      try {
        const voice = localStorage.getItem("evoloop_tts_voice") || undefined
        await invoke("start_wake_word_listener", { word, voice })
        if (!cancelled) { setIsListening(true); setError(null) }
      } catch (e: any) {
        if (!cancelled) { setError(e.message || String(e)); setIsListening(false) }
      }
    })()
    return () => { cancelled = true }
  }, [])

  const startListening = useCallback(async () => {
    if (!isTauri()) return
    try {
      const voice = localStorage.getItem("evoloop_tts_voice") || undefined
      await invoke("start_wake_word_listener", { word: wakeWord, voice })
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
      const saved = localStorage.getItem("evoloop_wake_word")
      if (saved) return saved
      return localStorage.getItem("evoloop_device_name") || "木头人"
    }
    return "木头人"
  })

  const [wakeWordEnabled, setWakeWordEnabled] = useState(() => {
    if (typeof window !== "undefined") {
      return localStorage.getItem("evoloop_wake_word_enabled") === "true"
    }
    return false
  })

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
