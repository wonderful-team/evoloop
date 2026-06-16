import { useCallback, useEffect, useRef, useState } from "react"

export interface VoiceRecorderState {
  isRecording: boolean
  duration: number
  volume: number
  error: string | null
}

export interface VoiceRecorderResult {
  blob: Blob
  duration: number
  waveform: number[]
}

export function useVoiceRecorder() {
  const [state, setState] = useState<VoiceRecorderState>({
    isRecording: false,
    duration: 0,
    volume: 0,
    error: null,
  })

  const mediaRecorderRef = useRef<MediaRecorder | null>(null)
  const audioContextRef = useRef<AudioContext | null>(null)
  const analyserRef = useRef<AnalyserNode | null>(null)
  const chunksRef = useRef<Blob[]>([])
  const timerRef = useRef<NodeJS.Timeout | null>(null)
  const volumeIntervalRef = useRef<NodeJS.Timeout | null>(null)
  const waveformRef = useRef<number[]>([])
  const startTimeRef = useRef<number>(0)

  // 清理函数
  const cleanup = useCallback(() => {
    if (timerRef.current) {
      clearInterval(timerRef.current)
      timerRef.current = null
    }
    if (volumeIntervalRef.current) {
      clearInterval(volumeIntervalRef.current)
      volumeIntervalRef.current = null
    }
    if (mediaRecorderRef.current) {
      mediaRecorderRef.current.stream
        .getTracks()
        .forEach((track) => track.stop())
      mediaRecorderRef.current = null
    }
    if (audioContextRef.current && audioContextRef.current.state !== "closed") {
      audioContextRef.current.close()
      audioContextRef.current = null
    }
    analyserRef.current = null
  }, [])

  useEffect(() => {
    return cleanup
  }, [cleanup])

  // 获取音量级别
  const getVolumeLevel = useCallback(() => {
    if (!analyserRef.current) return 0

    const dataArray = new Uint8Array(analyserRef.current.frequencyBinCount)
    analyserRef.current.getByteFrequencyData(dataArray)

    const average =
      dataArray.reduce((sum, value) => sum + value, 0) / dataArray.length
    return average / 255 // 归一化到 0-1
  }, [])

  // 开始录音
  const startRecording = useCallback(async () => {
    try {
      cleanup() // 确保清理之前的状态

      // 请求麦克风权限
      const stream = await navigator.mediaDevices.getUserMedia({
        audio: {
          echoCancellation: true,
          noiseSuppression: true,
          autoGainControl: true,
          sampleRate: 44100,
          channelCount: 1,
        },
      })

      // 创建音频上下文用于分析音量
      audioContextRef.current = new AudioContext()
      const source = audioContextRef.current.createMediaStreamSource(stream)
      analyserRef.current = audioContextRef.current.createAnalyser()
      analyserRef.current.fftSize = 256
      source.connect(analyserRef.current)

      // 创建 MediaRecorder
      const mimeType = MediaRecorder.isTypeSupported("audio/webm;codecs=opus")
        ? "audio/webm;codecs=opus"
        : MediaRecorder.isTypeSupported("audio/webm")
          ? "audio/webm"
          : "audio/mp4"

      mediaRecorderRef.current = new MediaRecorder(stream, {
        mimeType,
        audioBitsPerSecond: 128000,
      })

      chunksRef.current = []
      waveformRef.current = []
      startTimeRef.current = Date.now()

      mediaRecorderRef.current.ondataavailable = (e) => {
        if (e.data.size > 0) {
          chunksRef.current.push(e.data)
        }
      }

      // 开始录制
      mediaRecorderRef.current.start(100)

      // 启动计时器
      timerRef.current = setInterval(() => {
        const duration = Math.floor((Date.now() - startTimeRef.current) / 1000)
        setState((prev) => ({ ...prev, duration }))
      }, 1000)

      // 启动音量检测
      volumeIntervalRef.current = setInterval(() => {
        const volume = getVolumeLevel()
        waveformRef.current.push(volume)
        // 只保留最近 100 个样本（约 2 秒）
        if (waveformRef.current.length > 100) {
          waveformRef.current.shift()
        }
        setState((prev) => ({ ...prev, volume }))
      }, 50)

      setState({
        isRecording: true,
        duration: 0,
        volume: 0,
        error: null,
      })
    } catch (err: any) {
      console.error("Failed to start recording:", err)
      setState((prev) => ({
        ...prev,
        error:
          err.name === "NotAllowedError"
            ? "microphone_permission_denied"
            : err.message || "recording_failed",
      }))
      throw err
    }
  }, [cleanup, getVolumeLevel])

  // 停止录音
  const stopRecording = useCallback(async (): Promise<VoiceRecorderResult> => {
    return new Promise((resolve, reject) => {
      const mediaRecorder = mediaRecorderRef.current
      if (!mediaRecorder || mediaRecorder.state === "inactive") {
        reject(new Error("Not recording"))
        return
      }

      const finalDuration = Math.floor(
        (Date.now() - startTimeRef.current) / 1000,
      )
      const finalWaveform = [...waveformRef.current]

      mediaRecorder.onstop = () => {
        const mimeType = mediaRecorder.mimeType || "audio/webm"
        const blob = new Blob(chunksRef.current, { type: mimeType })

        cleanup()
        setState({
          isRecording: false,
          duration: 0,
          volume: 0,
          error: null,
        })

        resolve({
          blob,
          duration: finalDuration,
          waveform: finalWaveform,
        })
      }

      mediaRecorder.onerror = (_e) => {
        reject(new Error("Recording error"))
      }

      mediaRecorder.stop()
    })
  }, [cleanup])

  // 取消录音
  const cancelRecording = useCallback(() => {
    cleanup()
    setState({
      isRecording: false,
      duration: 0,
      volume: 0,
      error: null,
    })
  }, [cleanup])

  return {
    ...state,
    startRecording,
    stopRecording,
    cancelRecording,
  }
}
