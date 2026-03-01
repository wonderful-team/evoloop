import { Circle, Square, Monitor, ShieldAlert, Video } from "lucide-react"
import { toast } from "sonner"
import { useState, useEffect } from "react"
import { useTranslation } from "react-i18next"
import { MultimodalSynthesizeDialog } from "@/components/Learning/MultimodalSynthesizeDialog"
import { Badge } from "@evoloop/shared/components/ui/badge"
import { Button } from "@evoloop/shared/components/ui/button"
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@evoloop/shared/components/ui/tooltip"
import { useRecordingStore } from "@/stores/recordingStore"
import { useAccessibilityPermission } from "@/hooks/useAccessibilityPermission"
import { useScreenRecordingPermission } from "@/hooks/useScreenRecordingPermission"

interface RecordingButtonProps {
  threadId: string
  enabled?: boolean
}

export function RecordingButton({
  threadId,
  enabled = true,
}: RecordingButtonProps) {
  const { t } = useTranslation()
  const {
    isRecording,
    startRecording,
    stopRecording,
    eventCount,
    isGlobalMode,
    setIsGlobalMode,
    sessionId: storedSessionId,
    videoPath: storedVideoPath
  } = useRecordingStore()

  const [showSynthesizeDialog, setShowSynthesizeDialog] = useState(false)

  // Watch for session completion to show dialog
  useEffect(() => {
    if (!isRecording && storedSessionId) {
      // Logic to show dialog is handled here or in manager?
      // If we do it here, it might pop up on page load if session persists?
      // Better to have a local state tracking "did I just stop it?" or just handle the open logic
      // Actually, if we stopped and have a session ID, we probably want to synthesize.
      // But if we navigate away and back, we don't want it popping up again.
      // So let's only show it if we explicitly stop here? 
      // Or rely on the fact that sessionId remains in store until reset?
    }
  }, [isRecording, storedSessionId])

  const { hasPermission: hasAxPermission, requestPermission: requestAxPermission } = useAccessibilityPermission()
  const { hasPermission: hasVideoPermission, requestPermission: requestVideoPermission } = useScreenRecordingPermission()

  const handleStart = () => {
    console.log("[RecordingButton] handleStart clicked", { isGlobalMode, hasAxPermission, hasVideoPermission, threadId })

    // 1. Check Video Permission (Always needed)
    if (hasVideoPermission === false) {
      toast.error(t("learning.screenRecordingPermissionTitle", "Screen Recording Permission Required"))
      requestVideoPermission()
      return
    }

    // 2. Check AX Permission (Only if global)
    if (isGlobalMode && hasAxPermission === false) {
      console.log("[RecordingButton] Requesting AX permission...")
      toast.error(t("learning.permissionRequired", "Permission required. Check system settings."))
      requestAxPermission()
      return
    }
    console.log("[RecordingButton] Starting recording for thread:", threadId)
    startRecording(threadId)
  }

  const handleStop = () => {
    stopRecording()
    // The Manager handles the actual stop and session setting.
    // We can show the dialog when we detect session ID update?
    // Let's manually trigger dialog open 500ms later or via effect?
    // Actually, simple way: Manager sets sessionId.
    setTimeout(() => {
      // Check fresh state to verify if we actually captured anything AND session is valid
      const state = useRecordingStore.getState()
      if (state.eventCount > 0 && state.sessionId) {
        setShowSynthesizeDialog(true)
      }
    }, 1000)
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

      {/* AX Permission Indicator */}
      {isGlobalMode && hasAxPermission === false && !isRecording && (
        <div className="flex items-center">
          <Tooltip>
            <TooltipTrigger asChild>
              <Button
                variant="ghost"
                size="icon"
                className="h-8 w-8 text-amber-500 hover:text-amber-600"
                onClick={requestAxPermission}
              >
                <ShieldAlert className="h-4 w-4" />
              </Button>
            </TooltipTrigger>
            <TooltipContent>
              {t("learning.permissionRequired", "Accessibility permission required for global recording")}
            </TooltipContent>
          </Tooltip>
        </div>
      )}

      {/* Video Permission Indicator */}
      {hasVideoPermission === false && !isRecording && (
        <div className="flex items-center">
          <Tooltip>
            <TooltipTrigger asChild>
              <Button
                variant="ghost"
                size="icon"
                className="h-8 w-8 text-rose-500 hover:text-rose-600"
                onClick={requestVideoPermission}
              >
                <Video className="h-4 w-4" />
              </Button>
            </TooltipTrigger>
            <TooltipContent>
              {t("learning.screenRecordingPermissionTitle", "Screen recording permission required")}
            </TooltipContent>
          </Tooltip>
        </div>
      )}

      {/* Main Record Button */}
      <Tooltip>
        <TooltipTrigger asChild>
          <Button
            variant={isRecording ? "destructive" : "ghost"}
            size="sm"
            onClick={handleClick}
            // disabled={isGlobalMode && hasPermission === false} // Allow clicking to trigger permission request
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

      <MultimodalSynthesizeDialog
        open={showSynthesizeDialog}
        onOpenChange={setShowSynthesizeDialog}
        sessionId={storedSessionId || ""}
        threadId={threadId}
        videoPath={storedVideoPath}
      />
    </div>
  )
}
