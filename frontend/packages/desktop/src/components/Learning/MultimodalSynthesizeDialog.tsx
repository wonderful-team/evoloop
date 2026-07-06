import { Badge } from "@evoloop/shared/components/ui/badge"
import { Button } from "@evoloop/shared/components/ui/button"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@evoloop/shared/components/ui/dialog"
import { Input } from "@evoloop/shared/components/ui/input"
import { ScrollArea } from "@evoloop/shared/components/ui/scroll-area"
import { Textarea } from "@evoloop/shared/components/ui/textarea"
import {
  AlertTriangle,
  Crosshair,
  ExternalLink,
  FileVideo,
  Image as ImageIcon,
  Info,
  Loader2,
  Settings2,
  Sparkles,
  Trash2,
} from "lucide-react"
import { useCallback, useEffect, useState } from "react"
import { useTranslation } from "react-i18next"
import { toast } from "sonner"
import { LearningService } from "@/client/sdk.gen"
import type { AnnotationResponse } from "@/client/types.gen"
import { type SynthesisResult, useMultimodalSynthesis } from "@/hooks"
import { isTauri } from "@/lib/tauri"
import { useRecordingStore } from "@/stores/recordingStore"

interface MultimodalSynthesizeDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  sessionId: string
  threadId: string
  videoPath: string | null
  onSuccess?: () => void
  onOpenEditor?: (skillId: number) => void
  sourceType?: "desktop" | "android" // Source type for different persistence logic
}

export function MultimodalSynthesizeDialog({
  open,
  onOpenChange,
  sessionId,
  threadId,
  videoPath,
  onSuccess,
  onOpenEditor,
  sourceType = "desktop",
}: MultimodalSynthesizeDialogProps) {
  const { t } = useTranslation()
  const { reset: resetRecording, setSessionId } = useRecordingStore()
  const [taskDescription, setTaskDescription] = useState("")
  const [result, setResult] = useState<SynthesisResult | null>(null)
  const [editedName, setEditedName] = useState("")
  const [isUpdating, setIsUpdating] = useState(false)
  const [showCleanupConfirm, setShowCleanupConfirm] = useState(false)
  const [isCleaningUp, setIsCleaningUp] = useState(false)
  const [videoExists, setVideoExists] = useState<boolean | null>(null)
  const [annotations, setAnnotations] = useState<AnnotationResponse[]>([])
  const [isLoadingAnnotations, setIsLoadingAnnotations] = useState(false)

  // Fetch annotations when dialog opens
  useEffect(() => {
    if (!open || !sessionId) {
      setAnnotations([])
      return
    }

    const fetchAnnotations = async () => {
      setIsLoadingAnnotations(true)
      try {
        const data = await LearningService.listAnnotations({ sessionId })
        setAnnotations(data)
        console.log(
          `[MultimodalSynthesizeDialog] Loaded ${data.length} annotations`,
        )
      } catch (err) {
        console.error(
          "[MultimodalSynthesizeDialog] Failed to load annotations:",
          err,
        )
      } finally {
        setIsLoadingAnnotations(false)
      }
    }

    fetchAnnotations()
  }, [open, sessionId])

  // Check if video file exists when videoPath changes
  useEffect(() => {
    const checkVideoExists = async () => {
      if (!videoPath) {
        setVideoExists(null)
        return
      }
      if (!isTauri()) {
        setVideoExists(false)
        return
      }
      try {
        const { exists } = await import("@tauri-apps/plugin-fs")
        const fileExists = await exists(videoPath)
        setVideoExists(fileExists)
        console.log(
          `[MultimodalSynthesizeDialog] Video file check: ${videoPath} exists=${fileExists}`,
        )
      } catch (err) {
        console.error(
          `[MultimodalSynthesizeDialog] Error checking file existence:`,
          err,
        )
        setVideoExists(false)
      }
    }
    checkVideoExists()
  }, [videoPath])

  const { synthesize, isSynthesizing, progress } = useMultimodalSynthesis({
    onSuccess: (data) => {
      toast.success(t("learning.synthesisSuccess"))
      setResult(data)
      setEditedName(data.skill_name || "")
      onSuccess?.()
    },
    onError: (error) => {
      toast.error(t("learning.synthesisError"))
      console.error("Synthesis error:", error)
    },
  })

  const handleSynthesize = async () => {
    if (!videoPath) {
      toast.error(t("learning.noVideoPath"))
      return
    }
    if (!taskDescription.trim()) {
      toast.error(t("learning.taskDescriptionRequired"))
      return
    }

    // [Unified] All recordings now persist events in real-time to backend
    // Desktop/DOM/Global: events persisted via hooks (useGlobalRecorder, useActionRecorder)
    // Android: events persisted via MirrorService.persistEvents
    try {
      if (sourceType === "android") {
        // Android mirror: ensure events are persisted before synthesis
        // (they are buffered in mirror session until persistEvents is called)
        await LearningService.persistMirrorEvents({
          requestBody: { session_id: sessionId },
        })
        console.log(
          `[MultimodalSynthesizeDialog] Persisted Android mirror events for session ${sessionId}`,
        )
      }

      // [v3 Unified] Desktop recordings: events are already persisted in real-time by hooks
      // (via /global/events and /dom/events APIs)
      // Backend will read all events from DB by sessionId

      // Unified synthesis call - backend reads events from TraceEvent table by sessionId
      await synthesize({
        videoPath,
        sessionId,
        taskDescription: taskDescription.trim(),
        threadId,
        // events: undefined - backend reads from DB (unified with Android)
      })
    } catch (error) {
      console.error("[MultimodalSynthesizeDialog] Synthesis failed:", error)
      toast.error(t("learning.synthesisError"))
    }
  }

  const handleSaveAndClose = async () => {
    if (result?.skill_id && editedName && editedName !== result.skill_name) {
      setIsUpdating(true)
      try {
        const { LearningService } = await import("@/client/sdk.gen")
        await LearningService.updateSkill({
          skillId: result.skill_id,
          requestBody: { name: editedName },
        })
        onSuccess?.()
      } catch (error) {
        console.error("Update error:", error)
        toast.error(t("common.error.message"))
        setIsUpdating(false)
        return
      }
    }
    setResult(null)
    setEditedName("")
    setTaskDescription("")
    onOpenChange(false)
  }

  // Handle cancel click - show cleanup confirmation
  const handleCancelClick = () => {
    if (result) {
      // Already synthesized, just close without cleanup
      handleClose()
    } else {
      // Show cleanup confirmation
      setShowCleanupConfirm(true)
    }
  }

  // Perform cleanup and close
  const handleConfirmCleanup = async () => {
    setIsCleaningUp(true)
    try {
      // 1. Cleanup backend data first (events, annotations, jobs)
      if (sessionId) {
        try {
          await LearningService.cleanupRecordingSession({
            sessionId,
            videoPath: videoPath || undefined,
          })
          console.log(
            "[MultimodalSynthesizeDialog] Backend cleanup completed for session:",
            sessionId,
          )
        } catch (err) {
          console.warn(
            "[MultimodalSynthesizeDialog] Backend cleanup failed (may be already cleaned):",
            err,
          )
          // Continue with local cleanup even if backend fails
        }
      }

      // 2. Delete local video file using Tauri fs API
      if (videoPath && isTauri()) {
        try {
          const { remove } = await import("@tauri-apps/plugin-fs")
          await remove(videoPath)
          console.log(
            "[MultimodalSynthesizeDialog] Deleted video file:",
            videoPath,
          )
        } catch (err) {
          // File might not exist, that's ok
          console.warn(
            "[MultimodalSynthesizeDialog] Failed to delete video (might not exist):",
            err,
          )
        }
      }

      // 3. Clear session from store
      setSessionId(null)

      // 4. Reset recording store
      resetRecording()

      toast.success(t("learning.cleanupSuccess"))
      setShowCleanupConfirm(false)
      handleClose()
    } catch (error) {
      console.error("[MultimodalSynthesizeDialog] Cleanup failed:", error)
      toast.error(t("learning.cleanupFailed"))
    } finally {
      setIsCleaningUp(false)
    }
  }

  const handleClose = () => {
    setResult(null)
    setEditedName("")
    setTaskDescription("")
    setShowCleanupConfirm(false)
    onOpenChange(false)
  }

  // Handle click on video file to open with system player
  const handleOpenVideo = useCallback(async () => {
    if (!videoPath) {
      toast.error(t("learning.noVideoPath"))
      return
    }
    if (!isTauri()) {
      toast.info(t("learning.webVideoHint"))
      return
    }
    try {
      console.log("[MultimodalSynthesizeDialog] Opening video path:", videoPath)
      console.log(
        "[MultimodalSynthesizeDialog] Video exists check:",
        videoExists,
      )

      // First check if file exists
      const { exists } = await import("@tauri-apps/plugin-fs")
      const { openPath } = await import("@tauri-apps/plugin-opener")
      const fileExists = await exists(videoPath)
      if (!fileExists) {
        toast.error(t("learning.videoNotFoundWithPath", { path: videoPath }))
        console.error(
          "[MultimodalSynthesizeDialog] File does not exist:",
          videoPath,
        )
        return
      }

      // videoPath should already be absolute path from backend
      await openPath(videoPath)
      console.log("[MultimodalSynthesizeDialog] Opened video successfully")
    } catch (error: any) {
      console.error("[MultimodalSynthesizeDialog] Failed to open video:", error)
      const errorMsg = error?.message || String(error)
      toast.error(
        t("learning.openVideoFailedWithMessage", { message: errorMsg }),
      )
    }
  }, [videoPath, videoExists, t])

  return (
    <>
      <Dialog open={open} onOpenChange={handleClose} modal>
        <DialogContent
          className="sm:max-w-4xl max-h-[90vh] overflow-hidden"
          onPointerDownOutside={(e) => e.preventDefault()}
          onInteractOutside={(e) => e.preventDefault()}
        >
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              <Sparkles className="h-5 w-5 text-yellow-500" />
              {result
                ? t("learning.skillCreated")
                : t("learning.createSkillMultimodal")}
            </DialogTitle>
            <DialogDescription>
              {result
                ? t("learning.skillCreatedDesc")
                : t("learning.createSkillMultimodalDesc")}
            </DialogDescription>
          </DialogHeader>

          {result ? (
            <div className="py-4 space-y-4">
              <div className="grid gap-2">
                <label className="text-[10px] font-bold uppercase text-muted-foreground">
                  {t("learning.skillName")}
                </label>
                <Input
                  value={editedName}
                  onChange={(e) => setEditedName(e.target.value)}
                />
              </div>

              {result.skill_yaml && (
                <div className="bg-muted/30 p-3 rounded-lg border border-dashed text-xs text-muted-foreground">
                  <div className="flex items-center gap-1.5 font-bold mb-1 uppercase text-[10px]">
                    <Info className="h-3 w-3" /> {t("learning.skillYaml")}
                  </div>
                  <pre className="text-[10px] overflow-y-auto overflow-x-hidden max-h-32 whitespace-pre-wrap break-all">
                    {result.skill_yaml.slice(0, 500)}
                    {t("common.ellipsis")}
                  </pre>
                </div>
              )}

              <div className="grid grid-cols-3 gap-2 text-xs">
                <div className="bg-muted/20 p-2 rounded border text-center">
                  <div className="font-bold text-lg">
                    {result.frames_analyzed}
                  </div>
                  <div className="text-muted-foreground text-[10px]">
                    {t("learning.framesAnalyzed")}
                  </div>
                </div>
                <div className="bg-muted/20 p-2 rounded border text-center">
                  <div className="font-bold text-lg">
                    {result.events_processed}
                  </div>
                  <div className="text-muted-foreground text-[10px]">
                    {t("learning.eventsProcessed")}
                  </div>
                </div>
                <div className="bg-muted/20 p-2 rounded border text-center">
                  <div className="font-bold text-lg">
                    {result.processing_time_seconds.toFixed(1)}
                    {t("common.second")}
                  </div>
                  <div className="text-muted-foreground text-[10px]">
                    {t("learning.processingTime")}
                  </div>
                </div>
              </div>

              <div className="flex justify-center pt-2">
                <Button
                  variant="outline"
                  size="sm"
                  className="w-full gap-2 text-xs h-8 border-primary/20 hover:border-primary/50 text-primary"
                  onClick={() => {
                    if (result.skill_id) {
                      onOpenEditor?.(result.skill_id)
                    }
                    handleClose()
                  }}
                >
                  <Settings2 className="h-3.5 w-3.5" />
                  {t("learning.openFullEditor")}
                </Button>
              </div>
            </div>
          ) : (
            <div className="py-4 space-y-4">
              <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
                {/* Left Column - Form */}
                <div className="space-y-4">
                  {/* Recording Info */}
                  <button
                    type="button"
                    onClick={handleOpenVideo}
                    disabled={!videoPath || videoExists === false}
                    className={`w-full flex items-center gap-3 p-3 rounded-lg border cursor-pointer transition-colors text-left group ${
                      videoExists === false
                        ? "bg-destructive/10 border-destructive/30 hover:bg-destructive/20"
                        : "bg-muted/20 hover:bg-muted/30 disabled:opacity-50 disabled:cursor-not-allowed"
                    }`}
                  >
                    <div
                      className={`p-2 rounded transition-colors ${
                        videoExists === false
                          ? "bg-destructive/20 text-destructive"
                          : "bg-primary/10 group-hover:bg-primary/20"
                      }`}
                    >
                      <FileVideo
                        className={`h-4 w-4 ${videoExists === false ? "text-destructive" : "text-primary"}`}
                      />
                    </div>
                    <div className="flex-1 min-w-0">
                      <div className="text-xs font-medium truncate">
                        {videoPath
                          ? videoPath.split("/").pop()
                          : t("learning.noVideo")}
                      </div>
                      <div
                        className={`text-[10px] flex items-center gap-1 ${
                          videoExists === false
                            ? "text-destructive"
                            : "text-muted-foreground"
                        }`}
                      >
                        {videoPath ? (
                          videoExists === false ? (
                            <>
                              {t("learning.videoNotFound")}
                              <AlertTriangle className="h-3 w-3 inline" />
                            </>
                          ) : videoExists === null ? (
                            <>
                              <Loader2 className="h-3 w-3 inline animate-spin" />
                              {t("learning.checkingVideo")}
                            </>
                          ) : (
                            <>
                              {t("learning.clickToOpenVideo")}
                              <ExternalLink className="h-3 w-3 inline" />
                            </>
                          )
                        ) : (
                          t("learning.videoMissing")
                        )}
                      </div>
                    </div>
                  </button>

                  {/* Task Description Input */}
                  <div className="space-y-2">
                    <label className="text-xs font-medium">
                      {t("learning.taskDescription")}
                      <span className="text-destructive ml-1">*</span>
                    </label>
                    <Textarea
                      value={taskDescription}
                      onChange={(e) => setTaskDescription(e.target.value)}
                      placeholder={t("learning.taskDescriptionPlaceholder")}
                      className="min-h-[80px] text-sm"
                    />
                    <p className="text-[10px] text-muted-foreground">
                      {t(
                        "learning.taskDescriptionHelp",
                        "Describe the task clearly. AI will analyze the video and your actions to understand the workflow.",
                      )}
                    </p>
                  </div>

                  {/* Progress */}
                  {isSynthesizing && progress && (
                    <div className="flex items-center gap-2 text-sm text-muted-foreground">
                      <Loader2 className="h-4 w-4 animate-spin" />
                      {progress}
                    </div>
                  )}
                </div>

                {/* Right Column - Annotations */}
                <div className="space-y-3">
                  <div className="flex items-center justify-between">
                    <label className="text-xs font-medium flex items-center gap-1.5">
                      <ImageIcon className="h-3.5 w-3.5" />
                      {t("learning.regionAnnotations")}
                    </label>
                    {annotations.length > 0 && (
                      <Badge variant="secondary" className="text-[10px]">
                        {annotations.length}
                      </Badge>
                    )}
                  </div>

                  <ScrollArea className="h-[280px] rounded-lg border bg-muted/20">
                    {isLoadingAnnotations ? (
                      <div className="flex items-center justify-center h-full">
                        <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />
                      </div>
                    ) : annotations.length === 0 ? (
                      <div className="flex flex-col items-center justify-center h-full text-muted-foreground p-4">
                        <Crosshair className="h-8 w-8 mb-2 opacity-30" />
                        <p className="text-xs text-center">
                          {t("learning.noAnnotations")}
                        </p>
                        <p className="text-[10px] text-center mt-1 opacity-60">
                          {t("learning.noAnnotationsDesc")}
                        </p>
                      </div>
                    ) : (
                      <div className="p-3 space-y-3">
                        {annotations.map((annotation, index) => (
                          <div
                            key={annotation.id}
                            className="bg-background rounded-lg border p-3 space-y-2"
                          >
                            <div className="flex items-center justify-between">
                              <span className="text-[10px] font-medium text-muted-foreground">
                                {t("common.hash")}
                                {index + 1}
                              </span>
                              <span className="text-[10px] text-muted-foreground">
                                {annotation.video_timestamp_ms}
                                {t("common.millisecond")}
                              </span>
                            </div>

                            {/* Region Preview Box */}
                            {annotation.region && (
                              <div className="relative aspect-video bg-muted rounded border overflow-hidden">
                                {/* Visual representation of the region */}
                                <div
                                  className="absolute border-2 border-primary bg-primary/10"
                                  style={{
                                    left: `${(annotation.region.x || 0) * 100}%`,
                                    top: `${(annotation.region.y || 0) * 100}%`,
                                    width: `${(annotation.region.width || 0.1) * 100}%`,
                                    height: `${(annotation.region.height || 0.1) * 100}%`,
                                  }}
                                >
                                  <div className="absolute -top-5 left-0 bg-primary text-primary-foreground text-[9px] px-1 rounded">
                                    {Math.round(
                                      (annotation.region.width || 0) * 100,
                                    )}
                                    {t("common.percent")}{" "}
                                    {t("common.multiplicationSign")}{" "}
                                    {Math.round(
                                      (annotation.region.height || 0) * 100,
                                    )}
                                    {t("common.percent")}
                                  </div>
                                </div>
                              </div>
                            )}

                            {annotation.user_note && (
                              <p className="text-[10px] text-muted-foreground truncate">
                                {annotation.user_note}
                              </p>
                            )}
                          </div>
                        ))}
                      </div>
                    )}
                  </ScrollArea>
                </div>
              </div>
            </div>
          )}

          <DialogFooter>
            {result ? (
              <Button
                onClick={handleSaveAndClose}
                disabled={isUpdating}
                className="w-full"
              >
                {isUpdating && (
                  <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                )}
                {t("common.saveAndClose")}
              </Button>
            ) : (
              <div className="flex w-full gap-2">
                <Button
                  variant="outline"
                  onClick={handleCancelClick}
                  disabled={isSynthesizing}
                  className="flex-1"
                >
                  {t("common.cancel")}
                </Button>
                <Button
                  onClick={handleSynthesize}
                  disabled={
                    isSynthesizing || !videoPath || !taskDescription.trim()
                  }
                  className="flex-1"
                >
                  {isSynthesizing ? (
                    <Loader2 className="h-4 w-4 animate-spin" />
                  ) : (
                    <>
                      <Sparkles className="mr-2 h-4 w-4" />
                      {t("learning.synthesize")}
                    </>
                  )}
                </Button>
              </div>
            )}
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Cleanup Confirmation Dialog */}
      <Dialog
        open={showCleanupConfirm}
        onOpenChange={setShowCleanupConfirm}
        modal
      >
        <DialogContent
          className="sm:max-w-md"
          onPointerDownOutside={(e) => e.preventDefault()}
          onInteractOutside={(e) => e.preventDefault()}
        >
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2 text-destructive">
              <AlertTriangle className="h-5 w-5" />
              {t("learning.confirmCleanupTitle")}
            </DialogTitle>
            <DialogDescription>
              {t("learning.confirmCleanupDesc")}
            </DialogDescription>
          </DialogHeader>

          <div className="py-4">
            <div className="bg-muted/50 p-3 rounded-lg space-y-2 text-sm">
              <div className="flex items-center gap-2">
                <FileVideo className="h-4 w-4 text-muted-foreground" />
                <span className="text-muted-foreground">
                  {t("learning.videoFile")}
                </span>
              </div>
              <div className="flex items-center gap-2">
                <Trash2 className="h-4 w-4 text-muted-foreground" />
                <span className="text-muted-foreground">
                  {t("learning.recordedEvents")}
                </span>
              </div>
              <div className="flex items-center gap-2">
                <Trash2 className="h-4 w-4 text-muted-foreground" />
                <span className="text-muted-foreground">
                  {t("learning.annotations")}
                </span>
              </div>
            </div>
          </div>

          <DialogFooter className="gap-2">
            <Button
              variant="outline"
              onClick={() => setShowCleanupConfirm(false)}
              disabled={isCleaningUp}
            >
              {t("common.keep")}
            </Button>
            <Button
              variant="destructive"
              onClick={handleConfirmCleanup}
              disabled={isCleaningUp}
            >
              {isCleaningUp ? (
                <>
                  <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                  {t("common.deleting")}
                </>
              ) : (
                <>
                  <Trash2 className="mr-2 h-4 w-4" />
                  {t("common.discard")}
                </>
              )}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  )
}
