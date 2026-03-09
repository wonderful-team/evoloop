/**
 * SmartReplayEditor - Intelligent skill synthesis from annotated recordings
 *
 * Three-phase workflow:
 * 1. Annotation: User watches video and marks regions of interest
 * 2. Goal Description: User describes the task goal
 * 3. AI Synthesis: LLM analyzes and generates skill
 */

import { useCallback, useEffect, useRef, useState } from "react"
import { useTranslation } from "react-i18next"
import { toast } from "sonner"
import { convertFileSrc } from "@tauri-apps/api/core"
import {
    Loader2,
    Play,
    Pause,
    SkipBack,
    SkipForward,
    Square,
    MousePointer2,
    Trash2,
    ChevronRight,
    Sparkles,
    AlertCircle,
    CheckCircle2,
    X,
} from "lucide-react"

import { Button } from "@evoloop/shared/components/ui/button"
import { Textarea } from "@evoloop/shared/components/ui/textarea"
import { Input } from "@evoloop/shared/components/ui/input"
import { Badge } from "@evoloop/shared/components/ui/badge"
import { ScrollArea } from "@evoloop/shared/components/ui/scroll-area"
import { cn } from "@evoloop/shared/lib/utils"
import {
    Dialog,
    DialogContent,
    DialogDescription,
    DialogFooter,
    DialogHeader,
    DialogTitle,
} from "@evoloop/shared/components/ui/dialog"

import { AnnotationList } from "./AnnotationList"
import { Timeline } from "./Timeline"
import { SkillReviewPanel } from "./SkillReviewPanel"
import { SynthesisProgress } from "./SynthesisProgress"
import { LearningService } from "@/client/sdk.gen"

// Types
interface Annotation {
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

interface SmartReplayEditorProps {
    sessionId: string
    threadId?: string
    videoPath: string
    onComplete?: (skillId: number) => void
    onCancel?: () => void
}

type EditorPhase = "annotating" | "describing" | "synthesizing" | "reviewing"

export function SmartReplayEditor({
    sessionId,
    threadId,
    videoPath,
    onComplete,
    onCancel,
}: SmartReplayEditorProps) {
    const { t } = useTranslation()

    // Phase state
    const [phase, setPhase] = useState<EditorPhase>("annotating")

    // Video state
    const videoRef = useRef<HTMLVideoElement>(null)
    const [isPlaying, setIsPlaying] = useState(false)
    const [currentTime, setCurrentTime] = useState(0)
    const [duration, setDuration] = useState(0)
    const [videoSrc, setVideoSrc] = useState<string>("")

    // Convert video path to safe URL using Tauri's convertFileSrc
    useEffect(() => {
        if (videoPath) {
            try {
                // Convert local file path to safe URL for Tauri
                const safeUrl = convertFileSrc(videoPath)
                setVideoSrc(safeUrl)
                console.log("[SmartReplayEditor] Video path converted:", videoPath, "->", safeUrl)
            } catch (error) {
                console.error("[SmartReplayEditor] Failed to convert video path:", error)
                // Fallback to direct path (may not work in production)
                setVideoSrc(videoPath)
            }
        }
    }, [videoPath])

    // Annotation state
    const [annotations, setAnnotations] = useState<Annotation[]>([])
    const [isDrawing, setIsDrawing] = useState(false)
    const [selectionStart, setSelectionStart] = useState<{ x: number; y: number } | null>(null)
    const [selectionBox, setSelectionBox] = useState<{ x: number; y: number; width: number; height: number } | null>(null)
    const [activeAnnotation, setActiveAnnotation] = useState<number | null>(null)

    // Goal description state
    const [taskGoal, setTaskGoal] = useState("")

    // Synthesis state
    const [jobId, setJobId] = useState<number | null>(null)
    const [synthesisStatus, setSynthesisStatus] = useState<{
        status: string
        progress: number
        phase: string
        result?: any
        error?: any
    } | null>(null)

    // Close confirmation state
    const [showCloseConfirm, setShowCloseConfirm] = useState(false)
    const [deleteAssociatedFiles, setDeleteAssociatedFiles] = useState(true)

    // Handle close request
    const handleClose = useCallback(() => {
        setShowCloseConfirm(true)
    }, [])

    // Handle confirmed close
    const handleConfirmClose = useCallback(async () => {
        if (deleteAssociatedFiles) {
            try {
                // Delete all annotations first
                for (const annotation of annotations) {
                    if (annotation.id) {
                        await LearningService.deleteAnnotation({ annotationId: annotation.id })
                    }
                }
                toast.success(t("smartReplay.toast.filesDeleted"))
            } catch (error) {
                console.error("Failed to delete annotations:", error)
                toast.error(t("smartReplay.toast.deleteFailed"))
            }
        }
        setShowCloseConfirm(false)
        onCancel?.()
    }, [annotations, deleteAssociatedFiles, onCancel, t])

    // Handle cancel close dialog
    const handleCancelClose = useCallback(() => {
        setShowCloseConfirm(false)
        setDeleteAssociatedFiles(true)
    }, [])

    // Load video metadata
    useEffect(() => {
        const video = videoRef.current
        if (!video) return

        const handleLoaded = () => {
            setDuration(video.duration * 1000)
        }

        video.addEventListener("loadedmetadata", handleLoaded)
        return () => video.removeEventListener("loadedmetadata", handleLoaded)
    }, [videoPath])

    // Update current time
    useEffect(() => {
        const video = videoRef.current
        if (!video) return

        const handleTimeUpdate = () => {
            setCurrentTime(video.currentTime * 1000)
        }

        video.addEventListener("timeupdate", handleTimeUpdate)
        return () => video.removeEventListener("timeupdate", handleTimeUpdate)
    }, [])

    // Video controls
    const togglePlay = useCallback(() => {
        const video = videoRef.current
        if (!video) return

        if (isPlaying) {
            video.pause()
        } else {
            video.play()
        }
        setIsPlaying(!isPlaying)
    }, [isPlaying])

    const seek = useCallback((timeMs: number) => {
        const video = videoRef.current
        if (!video) return

        video.currentTime = timeMs / 1000
        setCurrentTime(timeMs)
    }, [])

    const skip = useCallback((direction: "forward" | "backward", amountMs: number = 5000) => {
        const newTime = direction === "forward"
            ? Math.min(currentTime + amountMs, duration)
            : Math.max(currentTime - amountMs, 0)
        seek(newTime)
    }, [currentTime, duration, seek])

    // Drawing handlers
    const handleMouseDown = useCallback((e: React.MouseEvent<HTMLDivElement>) => {
        if (!isDrawing) return

        const rect = e.currentTarget.getBoundingClientRect()
        const x = e.clientX - rect.left
        const y = e.clientY - rect.top

        setSelectionStart({ x, y })
        setSelectionBox({ x, y, width: 0, height: 0 })
    }, [isDrawing])

    const handleMouseMove = useCallback((e: React.MouseEvent<HTMLDivElement>) => {
        if (!isDrawing || !selectionStart) return

        const rect = e.currentTarget.getBoundingClientRect()
        const x = e.clientX - rect.left
        const y = e.clientY - rect.top

        setSelectionBox({
            x: Math.min(selectionStart.x, x),
            y: Math.min(selectionStart.y, y),
            width: Math.abs(x - selectionStart.x),
            height: Math.abs(y - selectionStart.y),
        })
    }, [isDrawing, selectionStart])

    const handleMouseUp = useCallback(() => {
        if (!isDrawing || !selectionBox) return

        if (selectionBox.width > 10 && selectionBox.height > 10) {
            const newAnnotation: Annotation = {
                video_timestamp_ms: Math.floor(currentTime),
                annotation_type: "extract_region",
                region: selectionBox,
            }
            setAnnotations([...annotations, newAnnotation])
            setActiveAnnotation(annotations.length)
        }

        setIsDrawing(false)
        setSelectionStart(null)
        setSelectionBox(null)
    }, [isDrawing, selectionBox, currentTime, annotations])

    // Save annotation to backend
    const saveAnnotation = useCallback(async (annotation: Annotation, index: number) => {
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

            const updated = [...annotations]
            updated[index] = { ...annotation, id: response.id }
            setAnnotations(updated)
        } catch (error) {
            console.error("Failed to save annotation:", error)
            toast.error(t("smartReplay.toast.saveAnnotationFailed"))
        }
    }, [sessionId, threadId, annotations])

    // Update annotation note
    const updateAnnotationNote = useCallback((index: number, note: string) => {
        const updated = [...annotations]
        updated[index] = { ...updated[index], user_note: note }
        setAnnotations(updated)

        if (updated[index].id) {
            saveAnnotation(updated[index], index)
        }
    }, [annotations, saveAnnotation])

    // Delete annotation
    const deleteAnnotation = useCallback(async (index: number) => {
        const annotation = annotations[index]

        if (annotation.id) {
            try {
                await LearningService.deleteAnnotation({ annotationId: annotation.id })
            } catch (error) {
                console.error("Failed to delete annotation:", error)
            }
        }

        const updated = annotations.filter((_, i) => i !== index)
        setAnnotations(updated)
        setActiveAnnotation(null)
    }, [annotations])

    // Start synthesis
    const startSynthesis = useCallback(async () => {
        if (!taskGoal.trim()) {
            toast.error(t("smartReplay.toast.describeGoalRequired"))
            return
        }

        setPhase("synthesizing")

        try {
            const response = await LearningService.startSmartSynthesis({
                sessionId,
                requestBody: {
                    session_id: sessionId,
                    thread_id: threadId,
                    task_goal: taskGoal,
                    annotation_ids: annotations
                        .filter(a => a.id)
                        .map(a => a.id!) || undefined,
                },
            })

            setJobId(response.job_id)
            pollSynthesisStatus(response.job_id)
        } catch (error) {
            console.error("Failed to start synthesis:", error)
            toast.error(t("smartReplay.toast.startSynthesisFailed"))
            setPhase("describing")
        }
    }, [sessionId, threadId, taskGoal, annotations])

    // Poll synthesis status
    const pollSynthesisStatus = useCallback(async (id: number) => {
        const poll = async () => {
            try {
                const status = await LearningService.getSynthesisJob({ jobId: id })

                setSynthesisStatus({
                    status: status.status,
                    progress: status.progress_percent,
                    phase: status.current_phase || "processing",
                    result: status.result,
                    error: status.error,
                })

                if (status.status === "completed") {
                    setPhase("reviewing")
                    return
                } else if (status.status === "failed") {
                    toast.error("Synthesis failed: " + (status.error?.message || "Unknown error"))
                    setPhase("describing")
                    return
                }

                setTimeout(poll, 2000)
            } catch (error) {
                console.error("Failed to get synthesis status:", error)
                setTimeout(poll, 5000)
            }
        }

        poll()
    }, [])

    // Complete and save skill
    const handleComplete = useCallback((result: { skill: any; macroScript: any[] }) => {
        // Call parent onComplete with skill info
        onComplete?.(result.skill.name)
    }, [onComplete])

    // Render close confirmation dialog
    const renderCloseConfirmDialog = () => (
        <Dialog open={showCloseConfirm} onOpenChange={setShowCloseConfirm}>
            <DialogContent className="sm:max-w-md">
                <DialogHeader>
                    <DialogTitle>{t("smartReplay.closeConfirmTitle")}</DialogTitle>
                    <DialogDescription>
                        {t("smartReplay.closeConfirmDesc")}
                    </DialogDescription>
                </DialogHeader>
                <div className="py-4">
                    <label className="flex items-center gap-3 p-3 border rounded-lg cursor-pointer hover:bg-muted/50 transition-colors">
                        <input
                            type="checkbox"
                            checked={deleteAssociatedFiles}
                            onChange={(e) => setDeleteAssociatedFiles(e.target.checked)}
                            className="w-4 h-4 rounded border-gray-300"
                        />
                        <div className="flex-1">
                            <p className="font-medium">{t("smartReplay.deleteAssociatedFiles")}</p>
                            <p className="text-sm text-muted-foreground">
                                {t("smartReplay.deleteFilesHint")}
                            </p>
                        </div>
                    </label>
                </div>
                <DialogFooter className="gap-2">
                    <Button variant="outline" onClick={handleCancelClose}>
                        {t("common.cancel")}
                    </Button>
                    <Button variant="destructive" onClick={handleConfirmClose}>
                        {t("smartReplay.closeAndDiscard")}
                    </Button>
                </DialogFooter>
            </DialogContent>
        </Dialog>
    )

    // Render different phases
    if (phase === "annotating") {
        return (
            <div className="flex flex-col h-full gap-4">
                {renderCloseConfirmDialog()}
                <div className="flex items-center justify-between">
                    <div>
                        <h2 className="text-lg font-semibold">{t("smartReplay.markRegions")}</h2>
                        <p className="text-sm text-muted-foreground">
                            {t("smartReplay.markRegionsDesc")}
                        </p>
                    </div>
                    <div className="flex items-center gap-2">
                        <Button
                            variant="ghost"
                            size="icon"
                            onClick={handleClose}
                            className="text-muted-foreground hover:text-foreground"
                        >
                            <X className="h-5 w-5" />
                        </Button>
                        <Button
                            onClick={() => setPhase("describing")}
                            disabled={annotations.length === 0}
                        >
                            {t("smartReplay.nextDescribeGoal")}
                            <ChevronRight className="ml-2 h-4 w-4" />
                        </Button>
                    </div>
                </div>

                <div className="flex-1 flex gap-4 min-h-0">
                    <div className="flex-1 flex flex-col gap-2">
                        <div
                            className="relative flex-1 bg-black rounded-lg overflow-hidden cursor-crosshair"
                            onMouseDown={handleMouseDown}
                            onMouseMove={handleMouseMove}
                            onMouseUp={handleMouseUp}
                            onMouseLeave={handleMouseUp}
                        >
                            {videoSrc ? (
                                <video
                                    ref={videoRef}
                                    src={videoSrc}
                                    className="w-full h-full object-contain"
                                    onClick={(e) => {
                                        if (!isDrawing) e.preventDefault()
                                    }}
                                    onError={(e) => {
                                        console.error("[SmartReplayEditor] Video failed to load:", videoSrc, e)
                                        toast.error(t("smartReplay.videoLoadFailed"))
                                    }}
                                    controls={false}
                                    playsInline
                                    preload="auto"
                                />
                            ) : (
                                <div className="w-full h-full flex items-center justify-center text-white/50">
                                    <div className="text-center">
                                        <Loader2 className="h-8 w-8 animate-spin mx-auto mb-2" />
                                        <p>{t("smartReplay.loadingVideo")}</p>
                                    </div>
                                </div>
                            )}

                            {selectionBox && (
                                <div
                                    className="absolute border-2 border-primary bg-primary/20"
                                    style={{
                                        left: selectionBox.x,
                                        top: selectionBox.y,
                                        width: selectionBox.width,
                                        height: selectionBox.height,
                                    }}
                                />
                            )}

                            {annotations.map((ann, idx) =>
                                ann.region && (
                                    <div
                                        key={idx}
                                        className={cn(
                                            "absolute border-2 cursor-pointer transition-all",
                                            activeAnnotation === idx
                                                ? "border-yellow-400 bg-yellow-400/30"
                                                : "border-green-400 bg-green-400/20 hover:bg-green-400/30"
                                        )}
                                        style={{
                                            left: ann.region.x,
                                            top: ann.region.y,
                                            width: ann.region.width,
                                            height: ann.region.height,
                                        }}
                                        onClick={() => setActiveAnnotation(idx)}
                                    >
                                        <Badge
                                            className="absolute -top-6 left-0 bg-green-500 text-white"
                                        >
                                            {idx + 1}
                                        </Badge>
                                    </div>
                                )
                            )}
                        </div>

                        <div className="flex items-center gap-2 p-2 bg-muted rounded-lg">
                            <Button
                                variant="ghost"
                                size="icon"
                                onClick={() => skip("backward")}
                            >
                                <SkipBack className="h-4 w-4" />
                            </Button>

                            <Button
                                variant={isPlaying ? "secondary" : "default"}
                                size="icon"
                                onClick={togglePlay}
                            >
                                {isPlaying ? (
                                    <Pause className="h-4 w-4" />
                                ) : (
                                    <Play className="h-4 w-4" />
                                )}
                            </Button>

                            <Button
                                variant="ghost"
                                size="icon"
                                onClick={() => skip("forward")}
                            >
                                <SkipForward className="h-4 w-4" />
                            </Button>

                            <div className="w-px h-6 bg-border mx-2" />

                            <Button
                                variant={isDrawing ? "default" : "outline"}
                                size="sm"
                                onClick={() => setIsDrawing(!isDrawing)}
                            >
                                <MousePointer2 className="mr-2 h-4 w-4" />
                                {isDrawing ? t("smartReplay.drawing") : t("smartReplay.drawRegion")}
                            </Button>

                            <div className="flex-1" />

                            <span className="text-sm text-muted-foreground font-mono">
                                {formatTime(currentTime)} / {formatTime(duration)}
                            </span>
                        </div>

                        <Timeline
                            duration={duration}
                            currentTime={currentTime}
                            annotations={annotations}
                            onSeek={seek}
                        />
                    </div>

                    <div className="w-80 flex flex-col gap-2">
                        <h3 className="font-medium">{t("smartReplay.annotationsCount", { count: annotations.length })}</h3>
                        <ScrollArea className="flex-1">
                            <AnnotationList
                                annotations={annotations}
                                activeIndex={activeAnnotation}
                                onSelect={(idx) => {
                                    setActiveAnnotation(idx)
                                    seek(annotations[idx].video_timestamp_ms)
                                }}
                                onUpdateNote={updateAnnotationNote}
                                onDelete={deleteAnnotation}
                            />
                        </ScrollArea>
                    </div>
                </div>
            </div>
        )
    }

    if (phase === "describing") {
        return (
            <div className="flex flex-col h-full max-w-2xl mx-auto gap-6 py-8 relative">
                {renderCloseConfirmDialog()}

                {/* Close button */}
                <div className="absolute top-0 right-0">
                    <Button
                        variant="ghost"
                        size="icon"
                        onClick={handleClose}
                        className="text-muted-foreground hover:text-foreground"
                    >
                        <X className="h-5 w-5" />
                    </Button>
                </div>

                <div className="text-center space-y-2">
                    <h2 className="text-2xl font-semibold">{t("smartReplay.describeGoal")}</h2>
                    <p className="text-muted-foreground">
                        {t("smartReplay.describeGoalDesc")}
                    </p>
                </div>

                <div className="bg-muted/50 p-4 rounded-lg space-y-2">
                    <h3 className="font-medium">{t("smartReplay.regionsMarked", { count: annotations.length })}</h3>
                    <ul className="space-y-1">
                        {annotations.map((ann, i) => (
                            <li key={i} className="text-sm flex items-center gap-2">
                                <Badge variant="outline">{i + 1}</Badge>
                                <span className="text-muted-foreground">
                                    {ann.user_note || t("smartReplay.noDescription")}
                                </span>
                                <span className="text-xs text-muted-foreground ml-auto">
                                    at {formatTime(ann.video_timestamp_ms)}
                                </span>
                            </li>
                        ))}
                    </ul>
                </div>

                <div className="space-y-2">
                    <label className="font-medium">{t("smartReplay.whatAccomplish")}</label>
                    <Textarea
                        value={taskGoal}
                        onChange={(e) => setTaskGoal(e.target.value)}
                        placeholder={t("smartReplay.taskGoalPlaceholder")}
                        rows={5}
                        className="resize-none"
                    />
                    <p className="text-sm text-muted-foreground">
                        {t("smartReplay.taskGoalHint")}
                    </p>
                </div>

                <div className="flex gap-2 justify-center">
                    <Button variant="outline" onClick={() => setPhase("annotating")}>
                        {t("smartReplay.backToAnnotations")}
                    </Button>
                    <Button
                        onClick={startSynthesis}
                        disabled={!taskGoal.trim()}
                        className="gap-2"
                    >
                        <Sparkles className="h-4 w-4" />
                        {t("smartReplay.startAiAnalysis")}
                    </Button>
                </div>
            </div>
        )
    }

    if (phase === "synthesizing") {
        return (
            <div className="flex flex-col h-full items-center justify-center gap-6 relative">
                {renderCloseConfirmDialog()}

                {/* Close button */}
                <div className="absolute top-0 right-0">
                    <Button
                        variant="ghost"
                        size="icon"
                        onClick={handleClose}
                        className="text-muted-foreground hover:text-foreground"
                    >
                        <X className="h-5 w-5" />
                    </Button>
                </div>

                <SynthesisProgress
                    status={synthesisStatus?.status || "processing"}
                    progress={synthesisStatus?.progress || 0}
                    phase={synthesisStatus?.phase || "initializing"}
                />

                <div className="text-center space-y-2">
                    <h2 className="text-xl font-semibold">{t("smartReplay.aiAnalyzing")}</h2>
                    <p className="text-muted-foreground max-w-md">
                        {t("smartReplay.aiAnalyzingDesc")}
                    </p>
                </div>

                {synthesisStatus?.phase && (
                    <Badge variant="secondary" className="text-sm">
                        {t("smartReplay.currentPhase", { phase: synthesisStatus.phase.replace(/_/g, " ") })}
                    </Badge>
                )}
            </div>
        )
    }

    if (phase === "reviewing" && synthesisStatus?.result?.skill) {
        return (
            <>
                {renderCloseConfirmDialog()}
                <SkillReviewPanel
                    skill={synthesisStatus.result.skill}
                    macroScript={synthesisStatus.result.skill.macro_script}
                    onEdit={() => setPhase("annotating")}
                    onComplete={handleComplete}
                    onCancel={handleClose}
                    videoPath={videoPath}
                />
            </>
        )
    }

    return null
}

function formatTime(ms: number): string {
    const totalSeconds = Math.floor(ms / 1000)
    const minutes = Math.floor(totalSeconds / 60)
    const seconds = totalSeconds % 60
    return `${minutes.toString().padStart(2, "0")}:${seconds.toString().padStart(2, "0")}`
}
