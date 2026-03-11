import { Circle, Square, Monitor, ShieldAlert, Video } from "lucide-react"
import { toast } from "sonner"
import { useCallback } from "react"
import { useTranslation } from "react-i18next"
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
    initiateRecording,
    stopRecording,
    eventCount,
    isGlobalMode,
    setIsGlobalMode,
    setPostRecordingAction,
  } = useRecordingStore()

  // Note: Synthesize dialog is handled by parent component (learning.tsx)
  // via postRecordingAction state, not here

  const { hasPermission: hasAxPermission, requestPermission: requestAxPermission } = useAccessibilityPermission()
  const { hasPermission: hasVideoPermission, requestPermission: requestVideoPermission } = useScreenRecordingPermission()

  const handleStart = useCallback(() => {
    console.log("[RecordingButton] handleStart clicked", { isGlobalMode, hasAxPermission, hasVideoPermission, threadId })

    // 1. Check Video Permission (Always needed)
    if (hasVideoPermission !== true) {
      toast.error(t("learning.screenRecordingPermissionTitle", "Screen Recording Permission Required"))
      requestVideoPermission()
      return
    }

    // 2. Check AX Permission (Only if global)
    if (isGlobalMode && hasAxPermission !== true) {
      console.log("[RecordingButton] Requesting AX permission...")
      toast.error(t("learning.permissionRequired", "Permission required. Check system settings."))
      requestAxPermission()
      return
    }

    // 3. Start countdown (countdown logic is now in store)
    initiateRecording(threadId)
  }, [hasVideoPermission, hasAxPermission, isGlobalMode, threadId, t, requestVideoPermission, requestAxPermission, initiateRecording])

  const handleStop = () => {
    // Must set action BEFORE stopping, so GlobalRecorderManager knows to trigger synthesis
    setPostRecordingAction('synthesize')
    stopRecording()
    // Synthesize dialog is handled by parent component (learning.tsx)
    // via postRecordingAction state
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

    </div>
  )
}
