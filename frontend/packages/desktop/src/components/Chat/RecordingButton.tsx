/**
 * RecordingButton - Visual control for imitation learning recording.
 *
 * Displays a pulsing record button when recording is active.
 * Shows event count and recording status.
 */

import { Circle, Square } from "lucide-react"
import { useState } from "react"
import { useTranslation } from "react-i18next"
import { toast } from "sonner"
import { SynthesizeSkillDialog } from "@/components/Learning/SynthesizeSkillDialog"
import { Badge } from "@evoloop/shared/components/ui/badge"
import { Button } from "@evoloop/shared/components/ui/button"
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@evoloop/shared/components/ui/tooltip"
import { useActionRecorder } from "@/hooks/useActionRecorder"

interface RecordingButtonProps {
  threadId: string
  taskName?: string
  enabled?: boolean
}

export function RecordingButton({
  threadId,
  taskName,
  enabled = true,
}: RecordingButtonProps) {
  const { t } = useTranslation()
  const [isStarting, setIsStarting] = useState(false)
  const [showSynthesizeDialog, setShowSynthesizeDialog] = useState(false)
  const [lastSessionId, setLastSessionId] = useState<string>("")

  const { isRecording, startRecording, stopRecording, eventCount } =
    useActionRecorder({
      threadId,
      taskName,
      enabled,
    })

  const handleClick = async () => {
    if (isRecording) {
      const sessionId = await stopRecording()
      toast.success(
        t(
          "learning.recordingStopped",
          `Recording stopped. ${eventCount} events captured.`,
        ),
      )

      if (sessionId) {
        setLastSessionId(sessionId)
        setShowSynthesizeDialog(true)
      }
    } else {
      setIsStarting(true)
      try {
        await startRecording()
        toast.info(
          t(
            "learning.recordingStarted",
            "Recording started. Your actions are being captured.",
          ),
        )
      } catch (_error) {
        toast.error(t("learning.recordingFailed", "Failed to start recording"))
      } finally {
        setIsStarting(false)
      }
    }
  }

  if (!enabled) return null

  return (
    <>
      <Tooltip>
        <TooltipTrigger asChild>
          <Button
            variant={isRecording ? "destructive" : "outline"}
            size="sm"
            onClick={handleClick}
            disabled={isStarting}
            className={`relative ${isRecording ? "animate-pulse" : ""}`}
          >
            {isRecording ? (
              <>
                <Square className="h-3 w-3 mr-1.5 fill-current" />
                <span>{t("learning.stopRecording", "Stop")}</span>
                <Badge variant="secondary" className="ml-2 text-xs">
                  {eventCount}
                </Badge>
              </>
            ) : (
              <>
                <Circle className="h-3 w-3 mr-1.5 text-red-500 fill-red-500" />
                <span>{t("learning.startRecording", "Record")}</span>
              </>
            )}
          </Button>
        </TooltipTrigger>
        <TooltipContent>
          {isRecording
            ? t(
                "learning.recordingTooltip",
                "Recording your actions for learning",
              )
            : t(
                "learning.startRecordingTooltip",
                "Start recording your actions",
              )}
        </TooltipContent>
      </Tooltip>

      <SynthesizeSkillDialog
        open={showSynthesizeDialog}
        onOpenChange={setShowSynthesizeDialog}
        sessionId={lastSessionId}
        threadId={threadId}
      />
    </>
  )
}
