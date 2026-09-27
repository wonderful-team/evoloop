import {useCallback, useState} from "react"
import {useTranslation} from "react-i18next"
import {LearningService} from "@/client/sdk.gen"

export interface SynthesisResult {
  success: boolean
  skill_id: number | null
  skill_name: string | null
  skill_yaml: string | null
  error: string | null
  processing_time_seconds: number
  frames_analyzed: number
  events_processed: number
}

interface UseMultimodalSynthesisOptions {
  onSuccess?: (result: SynthesisResult) => void
  onError?: (error: Error) => void
}

/**
 * 多模态 Skill 合成 Hook (v3 Unified)
 *
 * 从视频录制 + 事件序列合成 Expert Guide Skill
 * [v3] 事件统一通过实时 API 持久化到后端，合成时只需提供 sessionId
 *
 * 使用示例：
 * ```tsx
 * const { synthesize, isSynthesizing } = useMultimodalSynthesis({
 *   onSuccess: (result) => console.log("Created skill:", result.skill_name)
 * })
 *
 * // 停止录制后调用
 * const handleStopRecording = async () => {
 *   const videoPath = await stopScreenRecording()
 *   const sessionId = getCurrentSessionId()
 *
 *   await synthesize({
 *     videoPath,
 *     sessionId,
 *     taskDescription: "Send message to Zhang San in WeChat"
 *   })
 * }
 * ```
 */
export function useMultimodalSynthesis(
  options: UseMultimodalSynthesisOptions = {},
) {
  const { t } = useTranslation()
  const { onSuccess, onError } = options
  const [isSynthesizing, setIsSynthesizing] = useState(false)
  const [progress, setProgress] = useState<string>("")

  const synthesize = useCallback(
    async (params: {
      videoPath: string
      sessionId: string
      taskDescription: string
      threadId?: string
    }): Promise<SynthesisResult | null> => {
      setIsSynthesizing(true)
      setProgress(t("learning.synthesizingProgress"))

      try {
        const result = await LearningService.synthesizeFromRecording({
          requestBody: {
            video_path: params.videoPath,
            session_id: params.sessionId,
            task_description: params.taskDescription,
            thread_id: params.threadId,
            // [v3 Unified] Events are already persisted via real-time APIs
            // Backend reads from TraceEvent table by session_id
          },
        })

        if (result.success) {
          onSuccess?.(result as SynthesisResult)
          return result as SynthesisResult
        }
        throw new Error(result.error || t("learning.synthesisFailed"))
      } catch (error) {
        const err = error instanceof Error ? error : new Error(String(error))
        onError?.(err)
        return null
      } finally {
        setIsSynthesizing(false)
        setProgress("")
      }
    },
    [onSuccess, onError],
  )

  /**
   * 预览录制数据（调试用）
   */
  const previewRecording = useCallback(
    async (params: { videoPath: string; sessionId: string }) => {
      try {
        return await LearningService.previewRecordingData({
          sessionId: params.sessionId,
          videoPath: params.videoPath,
        })
      } catch (error) {
        console.error("Preview failed:", error)
        return null
      }
    },
    [],
  )

  return {
    synthesize,
    previewRecording,
    isSynthesizing,
    progress,
  }
}
