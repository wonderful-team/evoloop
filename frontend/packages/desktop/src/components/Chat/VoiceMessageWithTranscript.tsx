import { Button } from "@evoloop/shared/components/ui/button"
import { cn } from "@evoloop/shared/lib/utils"
import { Loader2, RotateCcw } from "lucide-react"
import { useCallback, useState } from "react"
import { useTranslation } from "react-i18next"
import { VoiceMessage } from "./VoiceMessage"

interface VoiceMessageWithTranscriptProps {
  audioUrl: string
  duration: number
  waveform?: number[]
  transcript?: string
  isTranscribing?: boolean
  onTranscribe?: () => Promise<string | null>
  isUser?: boolean
  className?: string
}

export function VoiceMessageWithTranscript({
  audioUrl,
  duration,
  waveform,
  transcript: initialTranscript,
  isTranscribing: initialTranscribing = false,
  onTranscribe,
  isUser = false,
  className,
}: VoiceMessageWithTranscriptProps) {
  const { t } = useTranslation()
  const [transcript, setTranscript] = useState<string | undefined>(
    initialTranscript,
  )
  const [isTranscribing, setIsTranscribing] = useState(initialTranscribing)
  const [isExpanded, setIsExpanded] = useState(false)

  const handleTranscribe = useCallback(async () => {
    if (!onTranscribe) return

    setIsTranscribing(true)
    try {
      const result = await onTranscribe()
      if (result) {
        setTranscript(result)
        setIsExpanded(true)
      }
    } finally {
      setIsTranscribing(false)
    }
  }, [onTranscribe])

  return (
    <div className={cn("flex flex-col gap-2", className)}>
      {/* 语音播放器 */}
      <VoiceMessage
        audioUrl={audioUrl}
        duration={duration}
        waveform={waveform}
        isUser={isUser}
      />

      {/* 转文字区域 */}
      <div
        className={cn(
          "rounded-lg overflow-hidden transition-all",
          isUser ? "bg-primary/10" : "bg-muted",
        )}
      >
        {/* 转文字按钮（如果还没有文字） */}
        {!transcript && !isTranscribing && onTranscribe && (
          <Button
            variant="ghost"
            size="sm"
            className={cn(
              "w-full h-8 text-xs",
              isUser
                ? "text-primary-foreground/70 hover:text-primary-foreground"
                : "text-muted-foreground",
            )}
            onClick={handleTranscribe}
          >
            {t("chat.voice.transcribe")}
          </Button>
        )}

        {/* 转文字中 */}
        {isTranscribing && (
          <div
            className={cn(
              "flex items-center justify-center gap-2 py-2 px-3",
              isUser ? "text-primary-foreground/70" : "text-muted-foreground",
            )}
          >
            <Loader2 className="w-3.5 h-3.5 animate-spin" />
            <span className="text-xs">{t("chat.voice.transcribing")}</span>
          </div>
        )}

        {/* 转文字结果 */}
        {transcript && (
          <div className="relative group">
            <button
              type="button"
              className={cn(
                "w-full text-left px-3 py-2 text-sm",
                isUser ? "text-primary-foreground/90" : "text-foreground",
              )}
              onClick={() => setIsExpanded(!isExpanded)}
            >
              <span
                className={cn("transition-all", !isExpanded && "line-clamp-2")}
              >
                {transcript}
              </span>
              {!isExpanded && transcript.length > 50 && (
                <span
                  className={cn(
                    "text-xs ml-1",
                    isUser
                      ? "text-primary-foreground/60"
                      : "text-muted-foreground",
                  )}
                >
                  {t("chat.voice.expand")}
                </span>
              )}
            </button>

            {/* 重新转文字按钮 */}
            {onTranscribe && (
              <Button
                variant="ghost"
                size="icon"
                className={cn(
                  "absolute right-1 top-1/2 -translate-y-1/2 w-6 h-6 opacity-0 group-hover:opacity-100 transition-opacity",
                  isUser
                    ? "text-primary-foreground/60 hover:text-primary-foreground"
                    : "text-muted-foreground",
                )}
                onClick={(e) => {
                  e.stopPropagation()
                  handleTranscribe()
                }}
                title={t("chat.voice.retranscribe")}
              >
                <RotateCcw className="w-3 h-3" />
              </Button>
            )}
          </div>
        )}
      </div>
    </div>
  )
}

/**
 * 语音消息转文字状态指示器
 */
export function TranscriptionBadge({
  status,
  onClick,
}: {
  status: "idle" | "transcribing" | "done" | "error"
  onClick?: () => void
}) {
  const { t } = useTranslation()

  if (status === "idle") {
    return (
      <button
        type="button"
        onClick={onClick}
        className="text-xs text-muted-foreground hover:text-foreground underline"
      >
        {t("chat.voice.transcribe")}
      </button>
    )
  }

  if (status === "transcribing") {
    return (
      <span className="text-xs text-muted-foreground flex items-center gap-1">
        <Loader2 className="w-3 h-3 animate-spin" />
        {t("chat.voice.transcribing")}
      </span>
    )
  }

  if (status === "done") {
    return (
      <span className="text-xs text-green-600">
        {t("chat.voice.transcribed")}
      </span>
    )
  }

  if (status === "error") {
    return (
      <button
        type="button"
        onClick={onClick}
        className="text-xs text-red-500 hover:text-red-600 underline"
      >
        {t("chat.voice.transcribeFailed")}
      </button>
    )
  }

  return null
}
