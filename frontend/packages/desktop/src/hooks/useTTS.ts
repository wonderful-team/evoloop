import { invoke } from "@tauri-apps/api/core"
import { useCallback, useEffect, useRef, useState } from "react"
import { useTranslation } from "react-i18next"
import { isTauri } from "@/lib/tauri"
import { toast } from "sonner"

export interface TTSOptions {
  voiceId?: string
  speed?: number
  format?: "mp3" | "opus" | "aac" | "flac"
  engine?: string
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
  fetchVoices: (engine?: string) => Promise<void>
}

export function useTTS(): UseTTSReturn {
  const { t } = useTranslation()
  const [isSpeaking, setIsSpeaking] = useState(false)
  const [isLoading, setIsLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const systemVoices: TTSVoice[] = [
    { id: "Ting-Ting", name: "Ting-Ting", gender: "female", description: "macOS 中文语音" },
    { id: "Samantha", name: "Samantha", gender: "female", description: "macOS English" },
  ]

  const edgeTtsVoices: TTSVoice[] = [
    { id: "zh-CN-XiaoxiaoNeural", name: "Xiaoxiao", gender: "female", description: t("settings.tts.voices.zhCNXiaoxiaoNeural") },
    { id: "zh-CN-YunxiNeural", name: "Yunxi", gender: "male", description: t("settings.tts.voices.zhCNYunxiNeural") },
    { id: "zh-CN-YunjianNeural", name: "Yunjian", gender: "male", description: t("settings.tts.voices.zhCNYunjianNeural") },
    { id: "zh-CN-XiaoyiNeural", name: "Xiaoyi", gender: "female", description: t("settings.tts.voices.zhCNXiaoyiNeural") },
    { id: "en-US-JennyNeural", name: "Jenny", gender: "female", description: "English (US), Jenny" },
    { id: "en-US-GuyNeural", name: "Guy", gender: "male", description: "English (US), Guy" },
  ]

  const qwenVoices: TTSVoice[] = [
    { id: "Cherry", name: "Cherry", gender: "female", description: "芊悦 (情感丰富女声)" },
    { id: "Serena", name: "Serena", gender: "female", description: "晴煦 (标准女声)" },
    { id: "Ethan", name: "Ethan", gender: "male", description: "晨煦 (标准男声)" },
    { id: "Sunny", name: "Sunny", gender: "female", description: "暖晴 (标准女声)" },
    { id: "Li", name: "Li", gender: "female", description: "李 (英文女声)" },
    { id: "Eric", name: "Eric", gender: "male", description: "埃里克 (英文男声)" },
  ]

  const engineVoices: Record<string, TTSVoice[]> = {
    "system": systemVoices,
    "edge-tts": edgeTtsVoices,
    "qwen-tts": qwenVoices,
  }

  const [voices, setVoices] = useState<TTSVoice[]>(edgeTtsVoices)
  const [currentVoice, setCurrentVoice] = useState("zh-CN-XiaoxiaoNeural")

  const audioRef = useRef<HTMLAudioElement | null>(null)
  const abortControllerRef = useRef<AbortController | null>(null)

  // Cleanup on unmount & sync Qwen key on mount
  useEffect(() => {
    if (isTauri()) {
      const key = localStorage.getItem("evoloop_qwen_tts_key") || ""
      if (key) {
        invoke("set_qwen_api_key", { key }).catch(console.error)
      }
    }
    return () => {
      stop()
    }
  }, [])

  const fetchVoices = useCallback(async (engine?: string) => {
    const eng = engine || "edge-tts"
    const list = engineVoices[eng] || edgeTtsVoices
    setVoices(list)
    // Auto-select first voice for the new engine
    if (list.length > 0) {
      const current = currentVoice
      const exists = list.some(v => v.id === current)
      if (!exists) {
        setCurrentVoice(list[0].id)
      }
    }
  }, [currentVoice])

  const stop = useCallback(async () => {
    if (isTauri()) {
      try {
        await invoke("stop_speaking")
      } catch (e) {
        console.error("Failed to stop speaking:", e)
      }
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
      await stop()
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
        await invoke("speak_text", { text, voice: voiceId, rate, engine: options.engine })
        setIsSpeaking(false)
        setIsLoading(false)
      } catch (err: any) {
        console.error("TTS error:", err)
        const errMsg = err.message || err.toString() || t("chat.tts.error")
        setError(errMsg)
        setIsSpeaking(false)
        setIsLoading(false)
        toast.error(t("chat.tts.error") + ": " + errMsg)
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
