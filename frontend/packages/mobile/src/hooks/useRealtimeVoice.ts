import { useCallback, useEffect, useRef, useState } from "react"
import i18n from "@evoloop/shared/i18n"
import { GatewayManager } from "../utils/gateway"

export interface VoiceEvent {
  type: string
  text?: string
  full_text?: string
  audio?: string
  intent?: any
  record_id?: number
  message?: string
  session_id?: number
  timestamp?: number
}

export interface UseRealtimeVoiceOptions {
  memberId: string
  threadId?: string
  projectId?: number
  onUserTranscript?: (text: string, fullText: string) => void
  onAiTranscript?: (text: string, fullText: string) => void
  onAiAudio?: (audioBase64: string) => void
  onActionDispatched?: (intent: any, recordId: number) => void
  onChatComplete?: (userText: string, aiText: string, recordId: number) => void
  onError?: (message: string) => void
  onSessionStarted?: (sessionId: number) => void
  onSessionEnded?: () => void
}

export interface VoiceState {
  isSessionActive: boolean
  isRecording: boolean
  isProcessing: boolean
  isAiSpeaking: boolean
  error: string | null
  userText: string
  aiText: string
}

/**
 * 实时语音通话 Hook
 * 连接 EvoCloud 语音服务，支持双向音频流
 */
export function useRealtimeVoice(options: UseRealtimeVoiceOptions) {
  const [state, setState] = useState<VoiceState>({
    isSessionActive: false,
    isRecording: false,
    isProcessing: false,
    isAiSpeaking: false,
    error: null,
    userText: "",
    aiText: "",
  })

  const mediaRecorderRef = useRef<MediaRecorder | null>(null)
  const audioContextRef = useRef<AudioContext | null>(null)
  const audioQueueRef = useRef<string[]>([])
  const isPlayingRef = useRef(false)
  const sessionIdRef = useRef<number | null>(null)
  const processingIntervalRef = useRef<NodeJS.Timeout | null>(null)

  // 更新状态辅助函数
  const updateState = useCallback(
    (updates: Partial<VoiceState>) => {
      setState((prev) => ({ ...prev, ...updates }))
    },
    [setState]
  )

  // 启动语音会话
  const startSession = useCallback(async () => {
    try {
      updateState({ error: null })

      // 确保 Gateway 连接
      await GatewayManager.connect()

      // 注册消息处理器
      GatewayManager.onMessage(
        "voice_session_started",
        (data: VoiceEvent) => {
          sessionIdRef.current = data.session_id ?? null
          updateState({ isSessionActive: true })
          options.onSessionStarted?.(data.session_id!)
        }
      )

      GatewayManager.onMessage("user_transcript", (data: VoiceEvent) => {
        updateState({ userText: data.full_text || data.text || "" })
        options.onUserTranscript?.(data.text || "", data.full_text || "")
      })

      GatewayManager.onMessage("user_transcript_complete", (data: VoiceEvent) => {
        updateState({ userText: data.text || "" })
      })

      GatewayManager.onMessage("ai_transcript", (data: VoiceEvent) => {
        updateState({ aiText: data.full_text || data.text || "" })
        options.onAiTranscript?.(data.text || "", data.full_text || "")
      })

      GatewayManager.onMessage("ai_transcript_complete", (data: VoiceEvent) => {
        updateState({ aiText: data.text || "" })
      })

      GatewayManager.onMessage("ai_audio", (data: VoiceEvent) => {
        if (data.audio) {
          audioQueueRef.current.push(data.audio)
          if (!isPlayingRef.current) {
            playNextAudio()
          }
          options.onAiAudio?.(data.audio)
        }
      })

      GatewayManager.onMessage("ai_audio_complete", () => {
        updateState({ isAiSpeaking: false })
      })

      GatewayManager.onMessage("voice_processing", () => {
        updateState({ isProcessing: true, isRecording: false })
      })

      GatewayManager.onMessage("chat_complete", (data: VoiceEvent) => {
        updateState({
          isProcessing: false,
          userText: data.user_text || "",
          aiText: data.ai_text || "",
        })
        options.onChatComplete?.(data.user_text || "", data.ai_text || "", data.record_id!)
      })

      GatewayManager.onMessage("action_dispatched", (data: VoiceEvent) => {
        updateState({ isProcessing: false })
        options.onActionDispatched?.(data.intent, data.record_id!)
      })

      GatewayManager.onMessage("voice_session_ended", () => {
        updateState({
          isSessionActive: false,
          isRecording: false,
          isProcessing: false,
          userText: "",
          aiText: "",
        })
        options.onSessionEnded?.()
      })

      GatewayManager.onMessage("error", (data: VoiceEvent) => {
        updateState({ error: data.message || i18n.t("common.error.unknown"), isProcessing: false })
        options.onError?.(data.message || i18n.t("common.error.unknown"))
      })

      // 发送会话开始消息
      GatewayManager.send({
        type: "voice_session_start",
        thread_id: options.threadId,
        project_id: options.projectId,
      })
    } catch (err: any) {
      updateState({ error: err.message || i18n.t("common.error.sessionStartFailed") })
      options.onError?.(err.message || i18n.t("common.error.sessionStartFailed"))
    }
  }, [options])

  // 开始录音
  const startRecording = useCallback(async () => {
    if (!state.isSessionActive) {
      await startSession()
    }

    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        audio: {
          sampleRate: 16000,
          channelCount: 1,
          echoCancellation: true,
          noiseSuppression: true,
          autoGainControl: true,
        },
      })

      // 创建 AudioContext 用于重采样
      const audioContext = new AudioContext({ sampleRate: 16000 })
      audioContextRef.current = audioContext

      const source = audioContext.createMediaStreamSource(stream)
      const processor = audioContext.createScriptProcessor(4096, 1, 1)

      processor.onaudioprocess = (e) => {
        if (!state.isRecording) return

        const inputData = e.inputBuffer.getChannelData(0)
        const pcmData = floatTo16BitPCM(inputData)
        const base64 = arrayBufferToBase64(pcmData)

        GatewayManager.send({
          type: "voice_audio_chunk",
          audio: base64,
        })
      }

      source.connect(processor)
      processor.connect(audioContext.destination)

      mediaRecorderRef.current = {
        stream,
        processor,
        source,
      } as any

      updateState({ isRecording: true, isAiSpeaking: false })

      // 清空之前的文本
      updateState({ userText: "", aiText: "" })
    } catch (err: any) {
      updateState({ error: i18n.t("common.error.microphoneAccess") + ": " + err.message })
      options.onError?.(i18n.t("common.error.microphoneAccess") + ": " + err.message)
    }
  }, [state.isSessionActive, startSession, updateState, options])

  // 停止录音（提交）
  const stopRecording = useCallback(() => {
    updateState({ isRecording: false })

    // 停止音频处理
    if (mediaRecorderRef.current) {
      const { stream, processor, source } = mediaRecorderRef.current as any
      source.disconnect()
      processor.disconnect()
      stream.getTracks().forEach((track: MediaStreamTrack) => track.stop())
      mediaRecorderRef.current = null
    }

    if (audioContextRef.current) {
      audioContextRef.current.close()
      audioContextRef.current = null
    }

    // 发送提交命令
    GatewayManager.send({ type: "voice_commit" })
  }, [updateState])

  // 打断 AI
  const interrupt = useCallback(() => {
    // 清空播放队列
    audioQueueRef.current = []
    isPlayingRef.current = false

    // 停止当前播放
    if (audioContextRef.current?.state === "running") {
      audioContextRef.current.suspend()
    }

    GatewayManager.send({ type: "voice_interrupt" })
    updateState({ isAiSpeaking: false })
  }, [updateState])

  // 结束会话
  const endSession = useCallback(() => {
    GatewayManager.send({ type: "voice_session_end" })

    // 清理资源
    if (mediaRecorderRef.current) {
      const { stream, processor, source } = mediaRecorderRef.current as any
      source?.disconnect()
      processor?.disconnect()
      stream?.getTracks().forEach((track: MediaStreamTrack) => track.stop())
      mediaRecorderRef.current = null
    }

    if (audioContextRef.current) {
      audioContextRef.current.close()
      audioContextRef.current = null
    }

    // 清空队列
    audioQueueRef.current = []
    isPlayingRef.current = false
    sessionIdRef.current = null

    updateState({
      isSessionActive: false,
      isRecording: false,
      isProcessing: false,
      isAiSpeaking: false,
      userText: "",
      aiText: "",
    })
  }, [updateState])

  // 播放音频队列
  const playNextAudio = useCallback(async () => {
    if (isPlayingRef.current || audioQueueRef.current.length === 0) {
      return
    }

    isPlayingRef.current = true
    updateState({ isAiSpeaking: true })

    const audioBase64 = audioQueueRef.current.shift()

    try {
      await playPCM16Audio(audioBase64!, audioContextRef.current)
    } catch (err) {
      console.error("播放音频失败:", err)
    }

    isPlayingRef.current = false

    // 继续播放队列
    if (audioQueueRef.current.length > 0) {
      playNextAudio()
    } else {
      updateState({ isAiSpeaking: false })
    }
  }, [updateState])

  // 清理定时器
  useEffect(() => {
    return () => {
      if (processingIntervalRef.current) {
        clearInterval(processingIntervalRef.current)
      }
      endSession()
    }
  }, [endSession])

  return {
    ...state,
    sessionId: sessionIdRef.current,
    startSession,
    startRecording,
    stopRecording,
    interrupt,
    endSession,
  }
}

// 辅助函数：Float32 转 16-bit PCM
function floatTo16BitPCM(input: Float32Array): ArrayBuffer {
  const output = new DataView(new ArrayBuffer(input.length * 2))
  for (let i = 0; i < input.length; i++) {
    const s = Math.max(-1, Math.min(1, input[i]))
    output.setInt16(i * 2, s < 0 ? s * 0x8000 : s * 0x7fff, true)
  }
  return output.buffer
}

// 辅助函数：ArrayBuffer 转 Base64
function arrayBufferToBase64(buffer: ArrayBuffer): string {
  const bytes = new Uint8Array(buffer)
  let binary = ""
  for (let i = 0; i < bytes.byteLength; i++) {
    binary += String.fromCharCode(bytes[i])
  }
  return btoa(binary)
}

// 播放 PCM16 音频（24kHz，Kimi 输出格式）
async function playPCM16Audio(
  base64Audio: string,
  audioContext: AudioContext | null
): Promise<void> {
  if (!audioContext) {
    audioContext = new AudioContext({ sampleRate: 24000 })
  }

  // 解码 base64
  const binary = atob(base64Audio)
  const bytes = new Uint8Array(binary.length)
  for (let i = 0; i < binary.length; i++) {
    bytes[i] = binary.charCodeAt(i)
  }

  // 转换为 Float32
  const pcm16 = new Int16Array(bytes.buffer)
  const float32 = new Float32Array(pcm16.length)
  for (let i = 0; i < pcm16.length; i++) {
    float32[i] = pcm16[i] / 32768
  }

  // 创建音频缓冲区（24kHz）
  const buffer = audioContext.createBuffer(1, float32.length, 24000)
  buffer.getChannelData(0).set(float32)

  // 播放
  const source = audioContext.createBufferSource()
  source.buffer = buffer
  source.connect(audioContext.destination)

  return new Promise((resolve) => {
    source.onended = resolve
    source.start()
  })
}
