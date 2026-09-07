import { Badge } from "@evoloop/shared/components/ui/badge"
import { Button } from "@evoloop/shared/components/ui/button"
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "@evoloop/shared/components/ui/tooltip"
import { Circle, ShieldAlert, Square, Video } from "lucide-react"
import { useCallback } from "react"
import { useTranslation } from "react-i18next"
import { toast } from "sonner"
import { useAccessibilityPermission } from "@/hooks/useAccessibilityPermission"
import { useScreenRecordingPermission } from "@/hooks/useScreenRecordingPermission"
import { useRecordingStore } from "@/stores/recordingStore"

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
    isDesktopRecording,
    setIsDesktopRecording,
    setPostRecordingAction,
  } = useRecordingStore()

  // Note: Synthesize dialog is handled by parent component (learning.tsx)
  // via postRecordingAction state, not here

  const {
    hasPermission: hasAxPermission,
    requestPermission: requestAxPermission,
    checkPermission: checkAxPermission,
  } = useAccessibilityPermission()
  const {
    hasPermission: hasVideoPermission,
    requestPermission: requestVideoPermission,
    checkPermission: checkVideoPermission,
  } = useScreenRecordingPermission()

  const handleStart = useCallback(async () => {
    console.log("[RecordingButton] handleStart clicked", {
      isDesktopRecording,
      hasAxPermission,
      hasVideoPermission,
      threadId,
    })

    // 1. Check Video Permission (Always needed).
    // Cached state can be null before the first focus-event check — force a
    // fresh check instead of treating "unknown" as "denied".
    const videoOk =
      hasVideoPermission === true || (await checkVideoPermission(true))
    if (!videoOk) {
      toast.error(t("learning.screenRecordingPermissionTitle"))
      requestVideoPermission()
      return
    }

    // 2. Check AX Permission (Only if desktop recording)
    if (isDesktopRecording && hasAxPermission !== true) {
      const axOk = await checkAxPermission(true)
      if (!axOk) {
        console.log("[RecordingButton] Requesting AX permission...")
        toast.error(t("learning.permissionRequired"))
        requestAxPermission()
        return
      }
    }

    // 3. Start countdown (countdown logic is now in store)
    initiateRecording(threadId)
  }, [
    hasVideoPermission,
    hasAxPermission,
    isDesktopRecording,
    threadId,
    t,
    checkVideoPermission,
    requestVideoPermission,
    checkAxPermission,
    requestAxPermission,
    initiateRecording,
  ])

  const handleStop = () => {
    // Must set action BEFORE stopping, so GlobalRecorderManager knows to trigger synthesis
    setPostRecordingAction("synthesize")
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

  if (!enabled) {
    return (
      <TooltipProvider delayDuration={100}>
        <Tooltip>
          <TooltipTrigger asChild>
            <Button
              variant="ghost"
              size="sm"
              disabled
              className="h-8 px-2 text-muted-foreground/30 cursor-not-allowed"
            >
              <Circle className="h-4 w-4 fill-current" />
            </Button>
          </TooltipTrigger>
          <TooltipContent>
            {t("learning.recordingRequiresThread")}
          </TooltipContent>
        </Tooltip>
      </TooltipProvider>
    )
  }

  return (
    <div className="flex items-center gap-1">
      {/* Scope Toggle - Only show when not recording */}
      {!isRecording && (
        <Tooltip>
          {/*<TooltipTrigger asChild>
            <Button
              variant="ghost"
              size="icon"
              className={`h-8 w-8 ${isDesktopRecording ? "text-blue-600 bg-blue-50 hover:bg-blue-100" : "text-muted-foreground"}`}
              onClick={() => setIsDesktopRecording(!isDesktopRecording)}
            >
              <Monitor className="h-4 w-4" />
            </Button>
          </TooltipTrigger>*/}
          <TooltipContent>
            {isDesktopRecording
              ? t("learning.desktopRecording")
              : t("learning.appRecording")}
          </TooltipContent>
        </Tooltip>
      )}

      {/* AX Permission Indicator */}
      {isDesktopRecording && hasAxPermission === false && !isRecording && (
        <div className="flex items-center">
          <Tooltip>
            <TooltipTrigger asChild>
              <Button
                variant="ghost"
                size="icon"
                className="h-8 w-8 text-warning hover:text-warning/80"
                onClick={requestAxPermission}
              >
                <ShieldAlert className="h-4 w-4" />
              </Button>
            </TooltipTrigger>
            <TooltipContent>{t("learning.permissionRequired")}</TooltipContent>
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
              {t("learning.screenRecordingPermissionTitle")}
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
                <Badge
                  variant="secondary"
                  className="px-1 py-0 h-4 text-[10px] min-w-[1.5rem]"
                >
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
            ? t("learning.stopRecording")
            : t("learning.startRecording")}
        </TooltipContent>
      </Tooltip>
    </div>
  )
}
