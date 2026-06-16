import { useCallback, useEffect, useRef, useState } from "react"
import { useTranslation } from "react-i18next"
import { AudioService, OpenAPI } from "@/client"

export interface TTSOptions {
  voiceId?: string
  speed?: number
  format?: "mp3" | "opus" | "aac" | "flac"
}

export interface TTSVoice {
  id: string
  name: string
  gender: string
  description: string
  preview?: string
}

interface UseTTSReturn {
  isSpeaking: boolean
  isLoading: boolean
  error: string | null
  voices: TTSVoice[]
  currentVoice: string
  setCurrentVoice: (voice: string) => void
  speak: (text: string, options?: TTSOptions) => Promise<void>
  stop: () => void
  fetchVoices: () => Promise<void>
}

export function useTTS(): UseTTSReturn {
  const { t } = useTranslation()
  const [isSpeaking, setIsSpeaking] = useState(false)
  const [isLoading, setIsLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [voices, setVoices] = useState<TTSVoice[]>([
    {
      id: "zh-CN-XiaoxiaoNeural",
      name: "Xiaoxiao",
      gender: "female",
      description: "Gentle and natural, highly recommended",
    },
    {
      id: "zh-CN-YunxiNeural",
      name: "Yunxi",
      gender: "male",
      description: "Young and sunny, highly recommended",
    },
    {
      id: "zh-CN-YunjianNeural",
      name: "Yunjian",
      gender: "male",
      description: "News broadcasting style",
    },
    {
      id: "zh-CN-XiaoyiNeural",
      name: "Xiaoyi",
      gender: "female",
      description: "Lively and young",
    },
  ])
  const [currentVoice, setCurrentVoice] = useState("zh-CN-XiaoxiaoNeural")

  const audioRef = useRef<HTMLAudioElement | null>(null)
  const abortControllerRef = useRef<AbortController | null>(null)

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      stop()
    }
  }, [])

  const fetchVoices = useCallback(async () => {
    try {
      const data = (await AudioService.listVoices()) as { voices: TTSVoice[] }
      if (data.voices && Array.isArray(data.voices)) {
        setVoices(data.voices)
      }
    } catch (err) {
      console.warn("Failed to fetch voices:", err)
      // Keep default voices
    }
  }, [])

  const stop = useCallback(() => {
    if (audioRef.current) {
      audioRef.current.pause()
      audioRef.current.src = ""
      audioRef.current = null
    }

    if (abortControllerRef.current) {
      abortControllerRef.current.abort()
      abortControllerRef.current = null
    }

    setIsSpeaking(false)
    setIsLoading(false)
  }, [])

  const speak = useCallback(
    async (text: string, options: TTSOptions = {}) => {
      // Stop any current playback
      stop()

      if (!text.trim()) return

      setIsLoading(true)
      setError(null)

      try {
        const voiceId = options.voiceId || currentVoice
        const speed = options.speed ?? 1.0
        const format = options.format || "mp3"

        // Use streaming endpoint for faster playback
        const formData = new FormData()
        formData.append("text", text)
        formData.append("voice_id", voiceId)
        formData.append("speed", speed.toString())
        formData.append("format", format)

        abortControllerRef.current = new AbortController()

        const response = await fetch(
          `${OpenAPI.BASE}/api/v1/audio/tts-stream`,
          {
            method: "POST",
            body: formData,
            signal: abortControllerRef.current.signal,
          },
        )

        if (!response.ok) {
          const errorData = await response.json().catch(() => ({}))
          throw new Error(errorData.detail || "TTS failed")
        }

        // Get audio blob from stream
        const blob = await response.blob()
        const url = URL.createObjectURL(blob)

        // Create and play audio
        const audio = new Audio(url)
        audioRef.current = audio

        // Set up event handlers
        audio.onended = () => {
          URL.revokeObjectURL(url)
          setIsSpeaking(false)
          setIsLoading(false)
        }

        audio.onerror = (e) => {
          URL.revokeObjectURL(url)
          console.error("Audio playback error:", e)
          setError(t("chat.tts.playbackError"))
          setIsSpeaking(false)
          setIsLoading(false)
        }

        setIsSpeaking(true)
        setIsLoading(false)

        await audio.play()
      } catch (err: any) {
        if (err.name === "AbortError") {
          // User cancelled, not an error
          return
        }

        console.error("TTS error:", err)
        setError(err.message || t("chat.tts.error"))
        setIsSpeaking(false)
        setIsLoading(false)
      }
    },
    [currentVoice, stop, t],
  )

  return {
    isSpeaking,
    isLoading,
    error,
    voices,
    currentVoice,
    setCurrentVoice,
    speak,
    stop,
    fetchVoices,
  }
}

// Hook for managing auto-speak settings
export function useAutoSpeak() {
  const [autoSpeak, setAutoSpeak] = useState(() => {
    if (typeof window !== "undefined") {
      return localStorage.getItem("evoloop_auto_speak") === "true"
    }
    return false
  })

  const toggleAutoSpeak = useCallback(() => {
    setAutoSpeak((prev) => {
      const newValue = !prev
      localStorage.setItem("evoloop_auto_speak", newValue.toString())
      return newValue
    })
  }, [])

  return { autoSpeak, toggleAutoSpeak, setAutoSpeak }
}

// Queue-based TTS for sequential playback
export function useTTSQueue() {
  const { speak, stop, isSpeaking, ...rest } = useTTS()
  const queueRef = useRef<string[]>([])
  const [queueLength, setQueueLength] = useState(0)

  const speakNext = useCallback(async () => {
    if (isSpeaking || queueRef.current.length === 0) return

    const text = queueRef.current.shift()
    setQueueLength(queueRef.current.length)

    if (text) {
      await speak(text)
      // After speaking, try to speak next
      speakNext()
    }
  }, [isSpeaking, speak])

  const enqueue = useCallback(
    (text: string) => {
      queueRef.current.push(text)
      setQueueLength(queueRef.current.length)
      speakNext()
    },
    [speakNext],
  )

  const clearQueue = useCallback(() => {
    queueRef.current = []
    setQueueLength(0)
    stop()
  }, [stop])

  return {
    ...rest,
    isSpeaking,
    queueLength,
    enqueue,
    clearQueue,
    stop,
  }
}
