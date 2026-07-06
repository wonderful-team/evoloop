import { useCallback, useEffect, useRef, useState } from "react"
import { useTranslation } from "react-i18next"

interface UseWakeWordOptions {
  wakeWord?: string
  onWake?: () => void
  enabled?: boolean
  language?: string
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
  const { t } = useTranslation()
  const {
    wakeWord = "你好 Evo",
    onWake,
    enabled = false,
    language = "zh-CN",
  } = options

  const [isListening, setIsListening] = useState(false)
  const [isWakeWordDetected, setIsWakeWordDetected] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [transcript, setTranscript] = useState("")

  const recognitionRef = useRef<SpeechRecognition | null>(null)
  const timeoutRef = useRef<NodeJS.Timeout | null>(null)

  // Initialize speech recognition
  useEffect(() => {
    if (!enabled || typeof window === "undefined") return

    // Check browser support
    const SpeechRecognition =
      window.SpeechRecognition || window.webkitSpeechRecognition
    if (!SpeechRecognition) {
      setError(t("voice.notSupported"))
      return
    }

    // Use any type to avoid TypeScript issues with SpeechRecognition
    const recognition: any = new SpeechRecognition()
    recognition.continuous = true
    recognition.interimResults = true
    recognition.lang = language

    recognition.onstart = () => {
      setIsListening(true)
      setError(null)
    }

    recognition.onend = () => {
      setIsListening(false)
      // Auto-restart if enabled
      if (enabled && !isWakeWordDetected) {
        setTimeout(() => {
          try {
            recognition.start()
          } catch (_e) {
            // Already started
          }
        }, 100)
      }
    }

    recognition.onerror = (event: any) => {
      if (event.error === "no-speech") {
        // Ignore no-speech errors
        return
      }
      setError(
        t("voice.recognitionErrorWithDetail", {
          message: t("voice.recognitionError"),
          detail: event.error,
        }),
      )
      setIsListening(false)
    }

    recognition.onresult = (event: any) => {
      let finalTranscript = ""
      let interimTranscript = ""

      for (let i = event.resultIndex; i < event.results.length; i++) {
        const transcript = event.results[i][0].transcript
        if (event.results[i].isFinal) {
          finalTranscript += transcript
        } else {
          interimTranscript += transcript
        }
      }

      const currentTranscript = finalTranscript || interimTranscript
      setTranscript(currentTranscript)

      // Check for wake word (case-insensitive)
      const normalizedTranscript = currentTranscript
        .toLowerCase()
        .replace(/\s+/g, " ")
        .trim()
      const normalizedWakeWord = wakeWord
        .toLowerCase()
        .replace(/\s+/g, " ")
        .trim()

      // Also check partial matches
      const wakeWordParts = normalizedWakeWord.split(" ")
      const transcriptParts = normalizedTranscript.split(" ")

      // Check if wake word is in transcript
      const isMatch =
        normalizedTranscript.includes(normalizedWakeWord) ||
        wakeWordParts.every((part) =>
          transcriptParts.some((tp) => tp.includes(part) || part.includes(tp)),
        )

      if (isMatch && !isWakeWordDetected) {
        setIsWakeWordDetected(true)
        onWake?.()

        // Reset after 3 seconds
        if (timeoutRef.current) {
          clearTimeout(timeoutRef.current)
        }
        timeoutRef.current = setTimeout(() => {
          setIsWakeWordDetected(false)
          setTranscript("")
        }, 3000)
      }
    }

    recognitionRef.current = recognition

    return () => {
      recognition.stop()
      if (timeoutRef.current) {
        clearTimeout(timeoutRef.current)
      }
    }
  }, [wakeWord, enabled, language, onWake, isWakeWordDetected])

  const startListening = useCallback(() => {
    if (recognitionRef.current && !isListening) {
      try {
        recognitionRef.current.start()
      } catch (e) {
        console.error("Failed to start recognition:", e)
      }
    }
  }, [isListening])

  const stopListening = useCallback(() => {
    if (recognitionRef.current) {
      recognitionRef.current.stop()
    }
    setIsListening(false)
    setIsWakeWordDetected(false)
    if (timeoutRef.current) {
      clearTimeout(timeoutRef.current)
    }
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

// Hook for managing wake word settings
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
