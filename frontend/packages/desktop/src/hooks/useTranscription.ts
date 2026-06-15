import { useCallback, useState } from "react"
import { AudioService } from "@/client"

export interface TranscriptionResult {
  text: string
  duration: number
  language: string
  confidence?: number
}

export interface UseTranscriptionOptions {
  language?: string
  model?: string
  prompt?: string
  provider?: "auto" | "funasr" | "whisper"
}

export function useTranscription(options: UseTranscriptionOptions = {}) {
  const [isTranscribing, setIsTranscribing] = useState(false)
  const [progress, setProgress] = useState(0)
  const [error, setError] = useState<string | null>(null)

  const transcribe = useCallback(
    async (
      audioBlob: Blob,
      customOptions?: Partial<UseTranscriptionOptions>,
    ): Promise<TranscriptionResult | null> => {
      setIsTranscribing(true)
      setProgress(0)
      setError(null)

      try {
        // 模拟进度
        const progressInterval = setInterval(() => {
          setProgress((prev) => Math.min(prev + 10, 90))
        }, 200)

        // 将 Blob 转换为 File
        const file = new File([audioBlob], "voice.webm", {
          type: audioBlob.type,
        })

        // 调用后端 API
        const result = (await AudioService.transcribeAudio({
          formData: {
            file: file,
            language: customOptions?.language || options.language || "auto",
            model: customOptions?.model || options.model || "auto",
            prompt: customOptions?.prompt || options.prompt || undefined,
            provider: customOptions?.provider || options.provider || "auto",
          },
        })) as TranscriptionResult

        clearInterval(progressInterval)
        setProgress(100)

        return result
      } catch (err: any) {
        console.error("Transcription error:", err)
        setError(err.message || "Transcription failed")
        return null
      } finally {
        setIsTranscribing(false)
      }
    },
    [options.language, options.model, options.prompt, options.provider],
  )

  const transcribeFile = useCallback(
    async (
      filePath: string,
      customOptions?: Partial<UseTranscriptionOptions>,
    ): Promise<TranscriptionResult | null> => {
      setIsTranscribing(true)
      setProgress(0)
      setError(null)

      try {
        // 读取本地文件
        const response = await fetch(filePath)
        const blob = await response.blob()

        return await transcribe(blob, customOptions)
      } catch (err: any) {
        console.error("Transcription error:", err)
        setError(err.message || "Transcription failed")
        return null
      } finally {
        setIsTranscribing(false)
      }
    },
    [transcribe],
  )

  return {
    isTranscribing,
    progress,
    error,
    transcribe,
    transcribeFile,
  }
}
