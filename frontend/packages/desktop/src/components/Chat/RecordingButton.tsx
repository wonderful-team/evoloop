import { Circle, Square, Monitor, ShieldAlert } from "lucide-react"
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
import { useGlobalRecorder } from "@/hooks/useGlobalRecorder"
import { useAccessibilityPermission } from "@/hooks/useAccessibilityPermission"

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

  // Scope State
  const [isGlobalMode, setIsGlobalMode] = useState(false)
  const { hasPermission, requestPermission } = useAccessibilityPermission()

  // DOM Recorder
  const domRecorder = useActionRecorder({
    threadId,
    taskName,
    enabled,
    scope: isGlobalMode ? "both" : "dom"
  })

  // Global Recorder
  const globalRecorder = useGlobalRecorder({
    threadId,
    sessionId: domRecorder.sessionId,
    enabled: isGlobalMode
  })

  // Unified State
  const isRecording = domRecorder.isRecording || globalRecorder.isRecording
  const eventCount = domRecorder.eventCount + globalRecorder.eventCount

  const handleStart = async () => {
    if (isGlobalMode && hasPermission === false) {
      requestPermission() // Just open settings, don't start yet
      return
    }

    setIsStarting(true)
    try {
      await domRecorder.startRecording()
      if (isGlobalMode) {
        await globalRecorder.startRecording()
      }
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

  const handleStop = async () => {
    setIsStarting(true) // Show loading state

    // Stop Global first
    if (isGlobalMode) {
      await globalRecorder.stopRecording()
    }

    // Stop DOM and get session
    const sessionId = await domRecorder.stopRecording()

    setIsStarting(false)

    toast.success(
      t(
        "learning.recordingStopped",
        {
          defaultValue: "Recording stopped. {{count}} events captured.",
          count: eventCount
        }
      ),
    )

    if (sessionId) {
      setLastSessionId(sessionId)
      setShowSynthesizeDialog(true)
    }
  }

  const handleClick = () => {
    if (isRecording) {
      handleStop()
    } else {
      handleStart()
    }
  }

  if (!enabled) return null

  return (
    <div className="flex items-center gap-1">
      {/* Scope Toggle - Only show when not recording */}
      {!isRecording && (
        <Tooltip>
          <TooltipTrigger asChild>
            <Button
              variant="ghost"
              size="icon"
              className={`h-8 w-8 ${isGlobalMode ? "text-blue-600 bg-blue-50 hover:bg-blue-100" : "text-muted-foreground"}`}
              onClick={() => setIsGlobalMode(!isGlobalMode)}
            >
              <Monitor className="h-4 w-4" />
            </Button>
          </TooltipTrigger>
          <TooltipContent>
            {isGlobalMode
              ? t("learning.globalMode", "System Monitoring Active (Global)")
              : t("learning.domMode", "App Only (DOM)")}
          </TooltipContent>
        </Tooltip>
      )}

      {/* Permission Indicator */}
      {isGlobalMode && hasPermission === false && !isRecording && (
        <Tooltip>
          <TooltipTrigger asChild>
            <Button
              variant="ghost"
              size="icon"
              className="h-8 w-8 text-amber-500 hover:text-amber-600"
              onClick={requestPermission}
            >
              <ShieldAlert className="h-4 w-4" />
            </Button>
          </TooltipTrigger>
          <TooltipContent>
            {t("learning.permissionRequired", "Permission required for global recording")}
          </TooltipContent>
        </Tooltip>
      )}

      {/* Main Record Button */}
      <Tooltip>
        <TooltipTrigger asChild>
          <Button
            variant={isRecording ? "destructive" : "ghost"}
            size="sm"
            onClick={handleClick}
            disabled={isStarting || (isGlobalMode && hasPermission === false)}
            className={`h-8 px-2 relative ${isRecording ? "animate-pulse" : "text-muted-foreground hover:text-destructive"}`}
          >
            {isRecording ? (
              <span className="flex items-center gap-1">
                <Square className="h-3 w-3 fill-current" />
                <Badge variant="secondary" className="px-1 py-0 h-4 text-[10px] min-w-[1.5rem]">
                  {eventCount}
                </Badge>
              </span>
            ) : (
              <Circle className="h-4 w-4 fill-current" />
            )}
          </Button>
        </TooltipTrigger>
        <TooltipContent>
          {isRecording
            ? t("learning.stopRecording", "Stop Recording")
            : t("learning.startRecording", "Start Recording")}
        </TooltipContent>
      </Tooltip>

      <SynthesizeSkillDialog
        open={showSynthesizeDialog}
        onOpenChange={setShowSynthesizeDialog}
        sessionId={lastSessionId}
        threadId={threadId}
      />
    </div>
  )
}
