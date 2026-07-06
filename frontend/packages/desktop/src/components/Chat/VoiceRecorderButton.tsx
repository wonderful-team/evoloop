import { Button } from "@evoloop/shared/components/ui/button"
import { cn } from "@evoloop/shared/lib/utils"
import { Mic, Square, X } from "lucide-react"
import {
  forwardRef,
  useCallback,
  useImperativeHandle,
  useRef,
  useState,
} from "react"
import { useTranslation } from "react-i18next"
import { toast } from "sonner"
import { useTTS } from "@/hooks/useTTS"
import { useVoiceRecorder } from "@/hooks/useVoiceRecorder"
import { ensureMicrophonePermission } from "@/utils/permissions"
import { formatDuration, saveVoiceRecording } from "@/utils/voiceStorage"

interface VoiceRecorderButtonProps {
  onVoiceRecorded: (params: {
    blob: Blob
    url: string
    path: string
    duration: number
    waveform: number[]
  }) => void
  disabled?: boolean
}

export interface VoiceRecorderButtonHandle {
  start: () => Promise<void>
  stop: () => Promise<void>
  cancel: () => void
}

// VoiceRecorderButton - 语音录音按钮
// 注意：前端不做权限控制，后端返回 403 时会由拦截器处理并显示升级提示
export const VoiceRecorderButton = forwardRef<
  VoiceRecorderButtonHandle,
  VoiceRecorderButtonProps
>(({ onVoiceRecorded, disabled = false }, ref) => {
  const { t } = useTranslation()
  const [isPressing, setIsPressing] = useState(false)
  const [showCancel, setShowCancel] = useState(false)
  const [isProcessing, setIsProcessing] = useState(false)
  const startY = useRef(0)
  const startX = useRef(0)

  const {
    isRecording,
    duration,
    volume,
    error,
    startRecording,
    stopRecording,
    cancelRecording,
  } = useVoiceRecorder()

  // TTS 控制，用于语音打断
  const { stop: stopTTS, isSpeaking } = useTTS()

  // 开始录音
  const handleStart = useCallback(
    async (clientY: number, clientX: number) => {
      if (disabled || isProcessing) return

      try {
        // 检查麦克风权限
        const hasPermission = await ensureMicrophonePermission()
        if (!hasPermission) {
          toast.error(t("chat.voice.permissionDenied"))
          return
        }

        // 语音打断：如果正在播放语音，先停止
        if (isSpeaking) {
          stopTTS()
        }

        startY.current = clientY
        startX.current = clientX

        await startRecording()
        setIsPressing(true)
        setShowCancel(false)
      } catch (err: any) {
        console.error("Failed to start recording:", err)
        toast.error(t("chat.voice.recordingFailed"))
      }
    },
    [disabled, isProcessing, startRecording, t, isSpeaking, stopTTS],
  )

  // 结束录音
  const handleEnd = useCallback(async () => {
    if (!isRecording || isProcessing) return

    setIsProcessing(true)

    try {
      if (showCancel) {
        // 取消录音
        cancelRecording()
        toast.info(t("chat.voice.cancelled"))
      } else {
        // 停止并保存录音
        const result = await stopRecording()

        // 太短不发送
        if (result.duration < 1) {
          toast.warning(t("chat.voice.tooShort"))
          return
        }

        // 保存到本地
        const saved = await saveVoiceRecording(result.blob)

        onVoiceRecorded({
          blob: result.blob,
          url: saved.url,
          path: saved.path,
          duration: result.duration,
          waveform: result.waveform,
        })
      }
    } catch (err) {
      console.error("Recording error:", err)
      toast.error(t("chat.voice.recordingError"))
    } finally {
      setIsProcessing(false)
      setIsPressing(false)
      setShowCancel(false)
    }
  }, [
    isRecording,
    isProcessing,
    showCancel,
    stopRecording,
    cancelRecording,
    onVoiceRecorded,
    t,
  ])

  // 暴露给外部调用的方法
  useImperativeHandle(ref, () => ({
    start: () => handleStart(0, 0),
    stop: () => handleEnd(),
    cancel: () => {
      cancelRecording()
      setIsPressing(false)
      setIsProcessing(false)
    },
  }))

  // 处理移动（上滑取消）
  const handleMove = useCallback(
    (clientY: number, clientX: number) => {
      if (!isRecording) return

      const diffY = startY.current - clientY
      const diffX = Math.abs(clientX - startX.current)

      // 上滑超过 80px 或左右滑动超过 100px 显示取消
      const shouldCancel = diffY > 80 || diffX > 100
      setShowCancel(shouldCancel)
    },
    [isRecording],
  )

  // 鼠标事件
  const onMouseDown = (e: React.MouseEvent) => {
    e.preventDefault()
    handleStart(e.clientY, e.clientX)
  }

  const onMouseUp = (e: React.MouseEvent) => {
    e.preventDefault()
    handleEnd()
  }

  const onMouseMove = (e: React.MouseEvent) => {
    handleMove(e.clientY, e.clientX)
  }

  const onMouseLeave = () => {
    if (isRecording) {
      handleEnd()
    }
  }

  // 触摸事件
  const onTouchStart = (e: React.TouchEvent) => {
    const touch = e.touches[0]
    handleStart(touch.clientY, touch.clientX)
  }

  const onTouchEnd = (e: React.TouchEvent) => {
    e.preventDefault()
    handleEnd()
  }

  const onTouchMove = (e: React.TouchEvent) => {
    const touch = e.touches[0]
    handleMove(touch.clientY, touch.clientX)
  }

  // 错误处理
  if (error === "microphone_permission_denied") {
    return (
      <Button
        variant="ghost"
        size="icon"
        className="h-10 w-10 rounded-full text-amber-500 hover:text-amber-600 hover:bg-amber-500/10"
        onClick={() => ensureMicrophonePermission()}
        disabled={disabled}
      >
        <Mic className="h-5 w-5" />
      </Button>
    )
  }

  return (
    <div className="relative">
      {/* 录音状态浮层 */}
      {(isPressing || isRecording) && (
        <div className="absolute bottom-full left-1/2 -translate-x-1/2 mb-4 z-50">
          <div
            className={cn(
              "flex flex-col items-center gap-3 px-6 py-4 rounded-2xl shadow-xl",
              "bg-slate-900/95 backdrop-blur text-white",
              "transition-all duration-200",
              showCancel && "bg-red-900/95",
            )}
          >
            {/* 时长 */}
            <div className="flex items-center gap-2">
              <div
                className={cn(
                  "w-2 h-2 rounded-full animate-pulse",
                  showCancel ? "bg-red-400" : "bg-red-500",
                )}
              />
              <span className="text-xl font-mono font-medium">
                {formatDuration(duration)}
              </span>
            </div>

            {/* 波形动画 */}
            <div className="flex items-end gap-[2px] h-10">
              {Array.from({ length: 24 }).map((_, i) => {
                // 使用 volume 和随机值模拟波形
                const height = isRecording
                  ? Math.max(
                      20,
                      Math.min(100, volume * 100 + Math.random() * 40),
                    )
                  : 20

                return (
                  <div
                    key={i}
                    className={cn(
                      "w-1 rounded-full transition-all duration-75",
                      showCancel ? "bg-red-400" : "bg-white/80",
                    )}
                    style={{
                      height: `${height}%`,
                      animationDelay: `${i * 0.03}s`,
                      opacity: 0.6 + (height / 100) * 0.4,
                    }}
                  />
                )
              })}
            </div>

            {/* 提示文字 */}
            <span
              className={cn(
                "text-sm font-medium",
                showCancel ? "text-red-300" : "text-white/70",
              )}
            >
              {showCancel
                ? t("chat.voice.releaseToCancel")
                : t("chat.voice.slideUpToCancel")}
            </span>

            {/* 取消图标（上滑时显示） */}
            {showCancel && (
              <div className="absolute -top-12 left-1/2 -translate-x-1/2">
                <div className="w-10 h-10 rounded-full bg-red-500 flex items-center justify-center">
                  <X className="w-5 h-5 text-white" />
                </div>
              </div>
            )}
          </div>
        </div>
      )}

      {/* 录音按钮 */}
      <Button
        variant="ghost"
        size="icon"
        className={cn(
          "h-10 w-10 rounded-full transition-all duration-200 select-none",
          isRecording
            ? "bg-red-500 text-white hover:bg-red-600 shadow-lg shadow-red-500/30"
            : "text-muted-foreground hover:text-foreground hover:bg-muted",
        )}
        onMouseDown={onMouseDown}
        onMouseUp={onMouseUp}
        onMouseMove={onMouseMove}
        onMouseLeave={onMouseLeave}
        onTouchStart={onTouchStart}
        onTouchEnd={onTouchEnd}
        onTouchMove={onTouchMove}
        disabled={disabled || isProcessing}
      >
        {isRecording ? (
          <Square className="h-4 w-4 fill-current" />
        ) : (
          <Mic className="h-5 w-5" />
        )}
      </Button>
    </div>
  )
})
