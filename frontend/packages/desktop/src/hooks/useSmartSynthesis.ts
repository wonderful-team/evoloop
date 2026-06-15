/**
 * useSmartSynthesis - Hook for managing smart replay synthesis workflow
 */

import { useCallback, useState } from "react"
import { toast } from "sonner"
import { LearningService } from "@/client/sdk.gen"

export interface Annotation {
  id?: number
  video_timestamp_ms: number
  annotation_type: "extract_region" | "click_point" | "task_boundary"
  region?: {
    x: number
    y: number
    width: number
    height: number
  }
  user_note?: string
}

export interface SynthesisStatus {
  jobId: number
  status: "pending" | "processing" | "completed" | "failed"
  progress: number
  phase: string
  result?: {
    skill: {
      name: string
      description: string
      namespace: string
      trigger_patterns: string[]
      instructions: string
      execution_mode: string
      macro_script: any[]
    }
  }
  error?: {
    message: string
    traceback?: string
  }
}

interface UseSmartSynthesisOptions {
  sessionId: string
  threadId?: string
}

export function useSmartSynthesis({
  sessionId,
  threadId,
}: UseSmartSynthesisOptions) {
  const [annotations, setAnnotations] = useState<Annotation[]>([])
  const [synthesisStatus, setSynthesisStatus] =
    useState<SynthesisStatus | null>(null)
  const [isLoading, setIsLoading] = useState(false)

  // Save annotation to backend
  const saveAnnotation = useCallback(
    async (annotation: Annotation): Promise<Annotation> => {
      try {
        const response = await LearningService.createAnnotation({
          requestBody: {
            session_id: sessionId,
            thread_id: threadId,
            annotation_type: annotation.annotation_type,
            video_timestamp_ms: annotation.video_timestamp_ms,
            region_x: annotation.region?.x,
            region_y: annotation.region?.y,
            region_width: annotation.region?.width,
            region_height: annotation.region?.height,
            user_note: annotation.user_note,
          },
        })

        const savedAnnotation: Annotation = {
          ...annotation,
          id: response.id,
        }

        setAnnotations((prev) => [...prev, savedAnnotation])
        return savedAnnotation
      } catch (error) {
        console.error("Failed to save annotation:", error)
        toast.error("Failed to save annotation")
        throw error
      }
    },
    [sessionId, threadId],
  )

  // Delete annotation
  const deleteAnnotation = useCallback(async (annotationId: number) => {
    try {
      await LearningService.deleteAnnotation({ annotationId })
      setAnnotations((prev) => prev.filter((a) => a.id !== annotationId))
    } catch (error) {
      console.error("Failed to delete annotation:", error)
      toast.error("Failed to delete annotation")
      throw error
    }
  }, [])

  // Update annotation note
  const updateAnnotationNote = useCallback(
    async (annotationId: number, note: string) => {
      // Note: Currently we don't have an update endpoint, so we just update locally
      // In a full implementation, we'd call an update API
      setAnnotations((prev) =>
        prev.map((a) =>
          a.id === annotationId ? { ...a, user_note: note } : a,
        ),
      )
    },
    [],
  )

  // Load annotations for session
  const loadAnnotations = useCallback(async () => {
    try {
      const response = await LearningService.listAnnotations({ sessionId })
      setAnnotations(
        response.map((a) => ({
          id: a.id,
          video_timestamp_ms: a.video_timestamp_ms,
          annotation_type: a.annotation_type as Annotation["annotation_type"],
          region: a.region
            ? {
                x: a.region.x!,
                y: a.region.y!,
                width: a.region.width!,
                height: a.region.height!,
              }
            : undefined,
          user_note: a.user_note || undefined,
        })),
      )
    } catch (error) {
      console.error("Failed to load annotations:", error)
      toast.error("Failed to load annotations")
    }
  }, [sessionId])

  // Start synthesis
  const startSynthesis = useCallback(
    async (taskGoal: string): Promise<number> => {
      setIsLoading(true)
      try {
        const annotationIds = annotations.filter((a) => a.id).map((a) => a.id!)

        const response = await LearningService.startSmartSynthesis({
          sessionId,
          requestBody: {
            session_id: sessionId,
            thread_id: threadId,
            task_goal: taskGoal,
            annotation_ids:
              annotationIds.length > 0 ? annotationIds : undefined,
          },
        })

        setSynthesisStatus({
          jobId: response.job_id,
          status: "pending",
          progress: 0,
          phase: "initializing",
        })

        return response.job_id
      } catch (error) {
        console.error("Failed to start synthesis:", error)
        toast.error("Failed to start synthesis")
        throw error
      } finally {
        setIsLoading(false)
      }
    },
    [sessionId, threadId, annotations],
  )

  // Poll synthesis status
  const pollSynthesisStatus = useCallback(
    async (
      jobId: number,
      onUpdate?: (status: SynthesisStatus) => void,
    ): Promise<SynthesisStatus> => {
      return new Promise((resolve, reject) => {
        const poll = async () => {
          try {
            const response = await LearningService.getSynthesisJob({ jobId })

            const status: SynthesisStatus = {
              jobId: response.id,
              status: response.status as SynthesisStatus["status"],
              progress: response.progress_percent,
              phase: response.current_phase || "processing",
              result: response.result,
              error: response.error,
            }

            setSynthesisStatus(status)
            onUpdate?.(status)

            if (response.status === "completed") {
              resolve(status)
              return
            }
            if (response.status === "failed") {
              reject(new Error(response.error?.message || "Synthesis failed"))
              return
            }

            // Continue polling
            setTimeout(poll, 2000)
          } catch (error) {
            console.error("Failed to poll synthesis status:", error)
            setTimeout(poll, 5000)
          }
        }

        poll()
      })
    },
    [],
  )

  // Reset state
  const reset = useCallback(() => {
    setAnnotations([])
    setSynthesisStatus(null)
    setIsLoading(false)
  }, [])

  return {
    annotations,
    synthesisStatus,
    isLoading,
    saveAnnotation,
    deleteAnnotation,
    updateAnnotationNote,
    loadAnnotations,
    startSynthesis,
    pollSynthesisStatus,
    reset,
  }
}
