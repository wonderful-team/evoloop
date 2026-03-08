import { Loader2, Sparkles, Info, Settings2, FileVideo, ExternalLink, Trash2, AlertTriangle } from "lucide-react"
import { useState, useCallback, useEffect } from "react"
import { useTranslation } from "react-i18next"
import { toast } from "sonner"
import { openPath } from "@tauri-apps/plugin-opener"
import { remove, exists } from "@tauri-apps/plugin-fs"
import { useMultimodalSynthesis, type SynthesisResult } from "@/hooks"
import { useRecordingStore } from "@/stores/recordingStore"
import { LearningService } from "@/client/sdk.gen"
import { MirrorService } from "@/services/mirror"
import { Input } from "@evoloop/shared/components/ui/input"
import { Button } from "@evoloop/shared/components/ui/button"
import { Textarea } from "@evoloop/shared/components/ui/textarea"
import {
    Dialog,
    DialogContent,
    DialogDescription,
    DialogFooter,
    DialogHeader,
    DialogTitle,
} from "@evoloop/shared/components/ui/dialog"

interface MultimodalSynthesizeDialogProps {
    open: boolean
    onOpenChange: (open: boolean) => void
    sessionId: string
    threadId: string
    videoPath: string | null
    onSuccess?: () => void
    onOpenEditor?: (skillId: number) => void
    sourceType?: 'desktop' | 'android'  // Source type for different persistence logic
}

export function MultimodalSynthesizeDialog({
    open,
    onOpenChange,
    sessionId,
    threadId,
    videoPath,
    onSuccess,
    onOpenEditor,
    sourceType = 'desktop',
}: MultimodalSynthesizeDialogProps) {
    const { t } = useTranslation()
    const { reset: resetRecording, localEvents, clearLocalEvents, setSessionId } = useRecordingStore()
    const [taskDescription, setTaskDescription] = useState("")
    const [result, setResult] = useState<SynthesisResult | null>(null)
    const [editedName, setEditedName] = useState("")
    const [isUpdating, setIsUpdating] = useState(false)
    const [showCleanupConfirm, setShowCleanupConfirm] = useState(false)
    const [isCleaningUp, setIsCleaningUp] = useState(false)
    const [videoExists, setVideoExists] = useState<boolean | null>(null)

    // Check if video file exists when videoPath changes
    useEffect(() => {
        const checkVideoExists = async () => {
            if (!videoPath) {
                setVideoExists(null)
                return
            }
            try {
                const fileExists = await exists(videoPath)
                setVideoExists(fileExists)
                console.log(`[MultimodalSynthesizeDialog] Video file check: ${videoPath} exists=${fileExists}`)
            } catch (err) {
                console.error(`[MultimodalSynthesizeDialog] Error checking file existence:`, err)
                setVideoExists(false)
            }
        }
        checkVideoExists()
    }, [videoPath])

    const { synthesize, isSynthesizing, progress } = useMultimodalSynthesis({
        onSuccess: (data) => {
            toast.success(t("learning.synthesisSuccess", "Skill created successfully!"))
            setResult(data)
            setEditedName(data.skill_name || "")
            onSuccess?.()
        },
        onError: (error) => {
            toast.error(t("learning.synthesisError", "An error occurred during synthesis"))
            console.error("Synthesis error:", error)
        },
    })

    const handleSynthesize = async () => {
        if (!videoPath) {
            toast.error(t("learning.noVideoPath", "No video recording found"))
            return
        }
        if (!taskDescription.trim()) {
            toast.error(t("learning.taskDescriptionRequired", "Please describe what you did in the recording"))
            return
        }

        // Persist events to backend before synthesizing (delayed persistence)
        try {
            if (sourceType === 'desktop') {
                // Desktop recording: persist local events from store
                // Persist DOM events
                if (localEvents.domEvents.length > 0) {
                    await LearningService.recordEvents({
                        requestBody: {
                            session_id: sessionId,
                            thread_id: threadId,
                            events: localEvents.domEvents,
                        }
                    })
                    console.log(`[MultimodalSynthesizeDialog] Persisted ${localEvents.domEvents.length} DOM events`)
                }

                // Persist global events
                if (localEvents.globalEvents.length > 0) {
                    await LearningService.recordGlobalEvents({
                        requestBody: {
                            thread_id: threadId,
                            session_id: sessionId,
                            events: localEvents.globalEvents,
                        }
                    })
                    console.log(`[MultimodalSynthesizeDialog] Persisted ${localEvents.globalEvents.length} global events`)
                }

                // Clear local events after successful persistence
                clearLocalEvents()
            } else if (sourceType === 'android') {
                // Android mirror: persist events from backend session
                await MirrorService.persistEvents(sessionId)
                console.log(`[MultimodalSynthesizeDialog] Persisted Android mirror events for session ${sessionId}`)
            }

            // Trigger keyframe extraction
            await LearningService.extractKeyframes({
                requestBody: {
                    session_id: sessionId,
                    video_path: videoPath,
                    thread_id: threadId,
                }
            })
            console.log("[MultimodalSynthesizeDialog] Keyframe extraction triggered")
        } catch (error) {
            console.error("[MultimodalSynthesizeDialog] Failed to persist events:", error)
            toast.error(t("learning.persistFailed", "Failed to save recording data"))
            return
        }

        await synthesize({
            videoPath,
            sessionId,
            taskDescription: taskDescription.trim(),
            threadId,
        })
    }

    const handleSaveAndClose = async () => {
        if (result?.skill_id && editedName && editedName !== result.skill_name) {
            setIsUpdating(true)
            try {
                const { LearningService } = await import("@/client/sdk.gen")
                await LearningService.updateSkill({
                    skillId: result.skill_id,
                    requestBody: { name: editedName }
                })
                onSuccess?.()
            } catch (error) {
                console.error("Update error:", error)
                toast.error(t("common.error.message", "Failed to update"))
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
            // Delete video file using Tauri fs API
            if (videoPath) {
                try {
                    await remove(videoPath)
                    console.log("[MultimodalSynthesizeDialog] Deleted video file:", videoPath)
                } catch (err) {
                    // File might not exist, that's ok
                    console.warn("[MultimodalSynthesizeDialog] Failed to delete video (might not exist):", err)
                }
            }

            // Clear local events (they were never persisted to backend)
            clearLocalEvents()

            // Clear session from store (events never went to backend, so no backend cleanup needed)
            setSessionId(null)

            // Reset recording store
            resetRecording()

            toast.success(t("learning.cleanupSuccess", "Recording data cleaned up"))
            setShowCleanupConfirm(false)
            handleClose()
        } catch (error) {
            console.error("[MultimodalSynthesizeDialog] Cleanup failed:", error)
            toast.error(t("learning.cleanupFailed", "Failed to cleanup recording data"))
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
            toast.error(t("learning.noVideoPath", "No video recording found"))
            return
        }
        try {
            console.log("[MultimodalSynthesizeDialog] Opening video path:", videoPath)
            console.log("[MultimodalSynthesizeDialog] Video exists check:", videoExists)

            // First check if file exists
            const fileExists = await exists(videoPath)
            if (!fileExists) {
                toast.error(t("learning.videoNotFound", "Video file not found at path: " + videoPath))
                console.error("[MultimodalSynthesizeDialog] File does not exist:", videoPath)
                return
            }

            // videoPath should already be absolute path from backend
            await openPath(videoPath)
            console.log("[MultimodalSynthesizeDialog] Opened video successfully")
        } catch (error: any) {
            console.error("[MultimodalSynthesizeDialog] Failed to open video:", error)
            const errorMsg = error?.message || String(error)
            toast.error(t("learning.openVideoFailed", "Failed to open video: " + errorMsg))
        }
    }, [videoPath, videoExists, t])

    return (
        <>
        <Dialog open={open} onOpenChange={handleClose} modal>
            <DialogContent
                className="sm:max-w-lg"
                onPointerDownOutside={(e) => e.preventDefault()}
                onInteractOutside={(e) => e.preventDefault()}
            >
                <DialogHeader>
                    <DialogTitle className="flex items-center gap-2">
                        <Sparkles className="h-5 w-5 text-yellow-500" />
                        {result
                            ? t("learning.skillCreated", "Skill Created")
                            : t("learning.createSkillMultimodal", "Create Skill from Recording")}
                    </DialogTitle>
                    <DialogDescription>
                        {result
                            ? t("learning.skillCreatedDesc", "Your skill has been created successfully.")
                            : t("learning.createSkillMultimodalDesc", "AI will analyze your screen recording and actions to create a reusable skill.")}
                    </DialogDescription>
                </DialogHeader>

                {result ? (
                    <div className="py-4 space-y-4">
                        <div className="grid gap-2">
                            <label className="text-[10px] font-bold uppercase text-muted-foreground">
                                {t("learning.skillName", "Skill Name")}
                            </label>
                            <Input value={editedName} onChange={(e) => setEditedName(e.target.value)} />
                        </div>

                        {result.skill_yaml && (
                            <div className="bg-muted/30 p-3 rounded-lg border border-dashed text-xs text-muted-foreground">
                                <div className="flex items-center gap-1.5 font-bold mb-1 uppercase text-[10px]">
                                    <Info className="h-3 w-3" /> {t("learning.skillYaml", "Skill Configuration")}
                                </div>
                                <pre className="text-[10px] overflow-auto max-h-32">{result.skill_yaml.slice(0, 500)}...</pre>
                            </div>
                        )}

                        <div className="grid grid-cols-3 gap-2 text-xs">
                            <div className="bg-muted/20 p-2 rounded border text-center">
                                <div className="font-bold text-lg">{result.frames_analyzed}</div>
                                <div className="text-muted-foreground text-[10px]">{t("learning.framesAnalyzed", "Frames")}</div>
                            </div>
                            <div className="bg-muted/20 p-2 rounded border text-center">
                                <div className="font-bold text-lg">{result.events_processed}</div>
                                <div className="text-muted-foreground text-[10px]">{t("learning.eventsProcessed", "Events")}</div>
                            </div>
                            <div className="bg-muted/20 p-2 rounded border text-center">
                                <div className="font-bold text-lg">{result.processing_time_seconds.toFixed(1)}s</div>
                                <div className="text-muted-foreground text-[10px]">{t("learning.processingTime", "Time")}</div>
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
                                {t("learning.openFullEditor", "Open Full Editor")}
                            </Button>
                        </div>
                    </div>
                ) : (
                    <div className="py-4 space-y-4">
                        {/* Recording Info */}
                        <button
                            type="button"
                            onClick={handleOpenVideo}
                            disabled={!videoPath || videoExists === false}
                            className={`w-full flex items-center gap-3 p-3 rounded-lg border cursor-pointer transition-colors text-left group ${
                                videoExists === false
                                    ? 'bg-destructive/10 border-destructive/30 hover:bg-destructive/20'
                                    : 'bg-muted/20 hover:bg-muted/30 disabled:opacity-50 disabled:cursor-not-allowed'
                            }`}
                        >
                            <div className={`p-2 rounded transition-colors ${
                                videoExists === false
                                    ? 'bg-destructive/20 text-destructive'
                                    : 'bg-primary/10 group-hover:bg-primary/20'
                            }`}>
                                <FileVideo className={`h-4 w-4 ${videoExists === false ? 'text-destructive' : 'text-primary'}`} />
                            </div>
                            <div className="flex-1 min-w-0">
                                <div className="text-xs font-medium truncate">
                                    {videoPath
                                        ? videoPath.split("/").pop()
                                        : t("learning.noVideo", "No video available")}
                                </div>
                                <div className={`text-[10px] flex items-center gap-1 ${
                                    videoExists === false ? 'text-destructive' : 'text-muted-foreground'
                                }`}>
                                    {videoPath ? (
                                        videoExists === false ? (
                                            <>
                                                {t("learning.videoNotFound", "File not accessible")}
                                                <AlertTriangle className="h-3 w-3 inline" />
                                            </>
                                        ) : videoExists === null ? (
                                            <>
                                                <Loader2 className="h-3 w-3 inline animate-spin" />
                                                {t("learning.checkingVideo", "Checking...")}
                                            </>
                                        ) : (
                                            <>
                                                {t("learning.clickToOpenVideo", "Click to open video")}
                                                <ExternalLink className="h-3 w-3 inline" />
                                            </>
                                        )
                                    ) : (
                                        t("learning.videoMissing", "Screen recording not found")
                                    )}
                                </div>
                            </div>
                        </button>

                        {/* Task Description Input */}
                        <div className="space-y-2">
                            <label className="text-xs font-medium">
                                {t("learning.taskDescription", "What did you do in this recording?")}
                                <span className="text-destructive ml-1">*</span>
                            </label>
                            <Textarea
                                value={taskDescription}
                                onChange={(e) => setTaskDescription(e.target.value)}
                                placeholder={t(
                                    "learning.taskDescriptionPlaceholder",
                                    "e.g., Send a message to Zhang San in WeChat, then attach a file from Desktop"
                                )}
                                className="min-h-[80px] text-sm"
                            />
                            <p className="text-[10px] text-muted-foreground">
                                {t(
                                    "learning.taskDescriptionHelp",
                                    "Describe the task clearly. AI will analyze the video and your actions to understand the workflow."
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
                )}

                <DialogFooter>
                    {result ? (
                        <Button onClick={handleSaveAndClose} disabled={isUpdating} className="w-full">
                            {isUpdating && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
                            {t("common.saveAndClose", "Save and Close")}
                        </Button>
                    ) : (
                        <div className="flex w-full gap-2">
                            <Button variant="outline" onClick={handleCancelClick} disabled={isSynthesizing} className="flex-1">
                                {t("common.cancel", "Cancel")}
                            </Button>
                            <Button
                                onClick={handleSynthesize}
                                disabled={isSynthesizing || !videoPath || !taskDescription.trim()}
                                className="flex-1"
                            >
                                {isSynthesizing ? (
                                    <Loader2 className="h-4 w-4 animate-spin" />
                                ) : (
                                    <>
                                        <Sparkles className="mr-2 h-4 w-4" />
                                        {t("learning.synthesize", "Synthesize")}
                                    </>
                                )}
                            </Button>
                        </div>
                    )}
                </DialogFooter>
            </DialogContent>
        </Dialog>

        {/* Cleanup Confirmation Dialog */}
        <Dialog open={showCleanupConfirm} onOpenChange={setShowCleanupConfirm} modal>
            <DialogContent
                className="sm:max-w-md"
                onPointerDownOutside={(e) => e.preventDefault()}
                onInteractOutside={(e) => e.preventDefault()}
            >
                <DialogHeader>
                    <DialogTitle className="flex items-center gap-2 text-destructive">
                        <AlertTriangle className="h-5 w-5" />
                        {t("learning.confirmCleanupTitle", "Discard Recording?")}
                    </DialogTitle>
                    <DialogDescription>
                        {t("learning.confirmCleanupDesc", "This will permanently delete the video file and all recorded events. This action cannot be undone.")}
                    </DialogDescription>
                </DialogHeader>

                <div className="py-4">
                    <div className="bg-muted/50 p-3 rounded-lg space-y-2 text-sm">
                        <div className="flex items-center gap-2">
                            <FileVideo className="h-4 w-4 text-muted-foreground" />
                            <span className="text-muted-foreground">{t("learning.videoFile", "Video file")}</span>
                        </div>
                        <div className="flex items-center gap-2">
                            <Trash2 className="h-4 w-4 text-muted-foreground" />
                            <span className="text-muted-foreground">{t("learning.recordedEvents", "Recorded events")}</span>
                        </div>
                        <div className="flex items-center gap-2">
                            <Trash2 className="h-4 w-4 text-muted-foreground" />
                            <span className="text-muted-foreground">{t("learning.annotations", "Annotations")}</span>
                        </div>
                    </div>
                </div>

                <DialogFooter className="gap-2">
                    <Button variant="outline" onClick={() => setShowCleanupConfirm(false)} disabled={isCleaningUp}>
                        {t("common.keep", "Keep")}
                    </Button>
                    <Button variant="destructive" onClick={handleConfirmCleanup} disabled={isCleaningUp}>
                        {isCleaningUp ? (
                            <>
                                <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                                {t("common.deleting", "Deleting...")}
                            </>
                        ) : (
                            <>
                                <Trash2 className="mr-2 h-4 w-4" />
                                {t("common.discard", "Discard")}
                            </>
                        )}
                    </Button>
                </DialogFooter>
            </DialogContent>
        </Dialog>
        </>
    )
}
