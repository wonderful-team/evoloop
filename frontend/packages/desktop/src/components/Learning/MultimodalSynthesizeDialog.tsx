import { Loader2, Sparkles, Info, Terminal, Settings2, Video, FileVideo } from "lucide-react"
import { useState } from "react"
import { useTranslation } from "react-i18next"
import { toast } from "sonner"
import { useMultimodalSynthesis, type SynthesisResult } from "@/hooks"
import { Input } from "@evoloop/shared/components/ui/input"
import { Button } from "@evoloop/shared/components/ui/button"
import { Badge } from "@evoloop/shared/components/ui/badge"
import { Textarea } from "@evoloop/shared/components/ui/textarea"
import {
    Dialog,
    DialogContent,
    DialogDescription,
    DialogFooter,
    DialogHeader,
    DialogTitle,
} from "@evoloop/shared/components/ui/dialog"
import { useRecordingStore } from "@/stores/recordingStore"

interface MultimodalSynthesizeDialogProps {
    open: boolean
    onOpenChange: (open: boolean) => void
    sessionId: string
    threadId: string
    videoPath: string | null
    onSuccess?: () => void
    onOpenEditor?: (skillId: number) => void
}

export function MultimodalSynthesizeDialog({
    open,
    onOpenChange,
    sessionId,
    threadId,
    videoPath,
    onSuccess,
    onOpenEditor,
}: MultimodalSynthesizeDialogProps) {
    const { t } = useTranslation()
    const [taskDescription, setTaskDescription] = useState("")
    const [result, setResult] = useState<SynthesisResult | null>(null)
    const [editedName, setEditedName] = useState("")
    const [isUpdating, setIsUpdating] = useState(false)

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

    const handleClose = () => {
        setResult(null)
        setEditedName("")
        setTaskDescription("")
        onOpenChange(false)
    }

    return (
        <Dialog open={open} onOpenChange={handleClose}>
            <DialogContent className="sm:max-w-lg">
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
                        <div className="flex items-center gap-3 bg-muted/20 p-3 rounded-lg border">
                            <div className="bg-primary/10 p-2 rounded">
                                <FileVideo className="h-4 w-4 text-primary" />
                            </div>
                            <div className="flex-1 min-w-0">
                                <div className="text-xs font-medium truncate">
                                    {videoPath
                                        ? videoPath.split("/").pop()
                                        : t("learning.noVideo", "No video available")}
                                </div>
                                <div className="text-[10px] text-muted-foreground">
                                    {videoPath
                                        ? t("learning.videoReady", "Video recording ready for analysis")
                                        : t("learning.videoMissing", "Screen recording not found")}
                                </div>
                            </div>
                        </div>

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
                            <Button variant="outline" onClick={handleClose} disabled={isSynthesizing} className="flex-1">
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
    )
}
