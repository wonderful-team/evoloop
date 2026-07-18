import { invoke } from "@tauri-apps/api/core"
import { useCallback, useEffect, useRef, useState } from "react"
import { useTranslation } from "react-i18next"
import { isTauri } from "@/lib/tauri"

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
      description: t("settings.tts.voices.zhCNXiaoxiaoNeural"),
    },
    {
      id: "zh-CN-YunxiNeural",
      name: "Yunxi",
      gender: "male",
      description: t("settings.tts.voices.zhCNYunxiNeural"),
    },
    {
      id: "zh-CN-YunjianNeural",
      name: "Yunjian",
      gender: "male",
      description: t("settings.tts.voices.zhCNYunjianNeural"),
    },
    {
      id: "zh-CN-XiaoyiNeural",
      name: "Xiaoyi",
      gender: "female",
      description: t("settings.tts.voices.zhCNXiaoyiNeural"),
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
    if (!isTauri()) return
    try {
      const tauriVoices = await invoke<any[]>("list_system_voices")
      if (tauriVoices && Array.isArray(tauriVoices)) {
        setVoices(tauriVoices as TTSVoice[])
      }
    } catch (err) {
      console.warn("Failed to fetch voices:", err)
    }
  }, [])

  const stop = useCallback(() => {
    if (isTauri()) {
      invoke("stop_speaking").catch(() => {})
    }

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
      stop()
      if (!text.trim()) return

      if (!isTauri()) {
        setError("TTS is only available in the desktop app")
        return
      }

      setIsLoading(true)
      setError(null)

      try {
        const voiceId = options.voiceId || currentVoice
        const speed = options.speed ?? 1.0
        const rate = Math.round(speed * 200) // convert 0.5-2.0 to say's rate
        await invoke("speak_text", { text, voice: voiceId, rate })
        setIsSpeaking(false)
        setIsLoading(false)
      } catch (err: any) {
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
