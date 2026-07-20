import { invoke } from "@tauri-apps/api/core"
import { useCallback, useEffect, useRef, useState } from "react"
import { useTranslation } from "react-i18next"
import { isTauri } from "@/lib/tauri"
import { toast } from "sonner"
import { useVoiceStore } from "@/stores/voiceStore"

function stripMarkdown(text: string): string {
  return text
    .replace(/```[\s\S]*?```/g, "")           // 代码块
    .replace(/`([^`]+)`/g, "$1")                // 行内代码
    .replace(/\[([^\]]+)\]\([^)]+\)/g, "$1")     // 链接 [text](url) → text
    .replace(/!\[([^\]]*)\]\([^)]+\)/g, "$1")    // 图片 ![alt](url) → alt
    .replace(/[*_]{1,3}([^*_]+)[*_]{1,3}/g, "$1") // 加粗/斜体 **text** *text*
    .replace(/~~(.+?)~~/g, "$1")                 // 删除线
    .replace(/^#{1,6}\s+/gm, "")                 // 标题
    .replace(/^>\s+/gm, "")                      // 引用
    .replace(/^[-*+]\s+/gm, "")                  // 无序列表
    .replace(/^\d+\.\s+/gm, "")                  // 有序列表
    .replace(/^\s*[-*_]\s*[-*_]\s*[-*_]*\s*$/gm, "") // 分隔线
    .replace(/\|/g, "")                          // 表格
    .replace(/[\u{1F600}-\u{1F64F}]/gu, "")      // Emoji: 表情
    .replace(/[\u{1F300}-\u{1F5FF}]/gu, "")      // Emoji: 符号
    .replace(/[\u{1F680}-\u{1F6FF}]/gu, "")      // Emoji: 交通
    .replace(/[\u{1F1E0}-\u{1F1FF}]/gu, "")      // Emoji: 国旗
    .replace(/[\u{2600}-\u{26FF}]/gu, "")         // Emoji: 杂项
    .replace(/[\u{2700}-\u{27BF}]/gu, "")         // Emoji: 装饰
    .replace(/[\u{FE00}-\u{FE0F}]/gu, "")         // 变体选择器
    .replace(/\u{200D}/gu, "")                    // 零宽连接符
    .replace(/\n{3,}/g, "\n\n")                  // 多余空行
    .trim()
}

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
  const isSpeaking = useVoiceStore((s) => s.ttsSpeaking)
  const isLoading = useVoiceStore((s) => s.ttsLoading)
  const { setTtsSpeaking, setTtsLoading } = useVoiceStore()
  const [error, setError] = useState<string | null>(null)
  const speakLockRef = useRef(false)

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

  const cosyVoiceVoices: TTSVoice[] = [
    { id: "中文女", name: "中文女", gender: "female", description: "CosyVoice 默认中文女声" },
    { id: "中文男", name: "中文男", gender: "male", description: "CosyVoice 默认中文男声" },
  ]

  const kokoroVoices: TTSVoice[] = [
    { id: "zf_xiaobei", name: "Xiaobei", gender: "female", description: "晓北 (Kokoro 中文)" },
    { id: "zf_xiaoni", name: "Xiaoni", gender: "female", description: "晓妮 (Kokoro 中文)" },
    { id: "zf_xiaoxiao", name: "Xiaoxiao", gender: "female", description: "晓晓 (Kokoro 中文)" },
    { id: "zf_xiaoyi", name: "Xiaoyi", gender: "female", description: "晓艺 (Kokoro 中文)" },
  ]

  const engineVoices: Record<string, TTSVoice[]> = {
    "system": systemVoices,
    "edge-tts": edgeTtsVoices,
    "qwen-tts": qwenVoices,
    "cosyvoice": cosyVoiceVoices,
    "kokoro": kokoroVoices,
  }

  const [voices, setVoices] = useState<TTSVoice[]>(edgeTtsVoices)
  const [currentVoice, setCurrentVoiceState] = useState(() => {
    const saved = localStorage.getItem("evoloop_tts_voice")
    if (saved) return saved
    return "zh-CN-XiaoxiaoNeural"
  })

  const setCurrentVoice = useCallback((voice: string) => {
    setCurrentVoiceState(voice)
    localStorage.setItem("evoloop_tts_voice", voice)
  }, [])

  const audioRef = useRef<HTMLAudioElement | null>(null)
  const abortControllerRef = useRef<AbortController | null>(null)

  const fetchVoices = useCallback(async (engine?: string, targetVoice?: string) => {
    const eng = engine || localStorage.getItem("evoloop_tts_engine") || "edge-tts"
    const list = engineVoices[eng] || edgeTtsVoices
    setVoices(list)
    if (list.length > 0) {
      const voiceToMatch = targetVoice || currentVoice
      const exists = list.some(v => v.id === voiceToMatch)
      if (exists) {
        setCurrentVoiceState(voiceToMatch)
      } else {
        setCurrentVoiceState(list[0].id)
      }
    }
  }, [currentVoice])

  // Cleanup on unmount & sync engine / voice / Qwen key on mount
  useEffect(() => {
    const savedEngine = localStorage.getItem("evoloop_tts_engine")
    const savedVoice = localStorage.getItem("evoloop_tts_voice")
    if (savedVoice) {
      setCurrentVoiceState(savedVoice)
    }
    if (isTauri()) {
      const key = localStorage.getItem("evoloop_qwen_tts_key") || ""
      if (key) {
        invoke("set_qwen_api_key", { key }).catch(console.error)
      }
      if (savedEngine) {
        invoke("set_tts_engine", { engine: savedEngine }).catch(console.error)
      }
      if (savedVoice) {
        invoke("set_tts_voice", { voice: savedVoice }).catch(console.error)
      }
      const savedSpeed = localStorage.getItem("evoloop_tts_speed")
      if (savedSpeed) {
        invoke("set_tts_speed", { speed: parseFloat(savedSpeed) }).catch(console.error)
      }

      invoke<string>("get_tts_engine").then(eng => {
        const activeEngine = eng || savedEngine || "edge-tts"
        fetchVoices(activeEngine, savedVoice || undefined)
      }).catch(() => {
        if (savedEngine) {
          fetchVoices(savedEngine, savedVoice || undefined)
        }
      })
    } else if (savedEngine) {
      fetchVoices(savedEngine, savedVoice || undefined)
    }
    return () => {
      stop()
    }
  }, [])

  const stop = useCallback(async () => {
    speakLockRef.current = false
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

    setTtsSpeaking(false)
    setTtsLoading(false)
  }, [setTtsSpeaking, setTtsLoading])

  const speak = useCallback(
    async (text: string, options: TTSOptions = {}) => {
      if (speakLockRef.current) return
      speakLockRef.current = true
      try {
        await stop()
        const clean = stripMarkdown(text)
        if (!clean.trim()) return

        if (!isTauri()) {
          setError("TTS is only available in the desktop app")
          return
        }

        setTtsLoading(true)
        setError(null)

        setTtsSpeaking(true)
        await invoke("speak", {
          text: clean,
          engine: options.engine || null,
          voice: options.voiceId || null,
        })
        setTtsSpeaking(false)
        setTtsLoading(false)
      } catch (err: any) {
        console.error("TTS error:", err)
        const errMsg = err.message || err.toString() || t("chat.tts.error")
        setError(errMsg)
        setTtsSpeaking(false)
        setTtsLoading(false)
        toast.error(t("chat.tts.error") + ": " + errMsg)
      } finally {
        speakLockRef.current = false
      }
    },
    [stop, t, setTtsSpeaking, setTtsLoading],
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
