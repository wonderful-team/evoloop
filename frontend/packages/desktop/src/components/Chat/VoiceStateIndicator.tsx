import { cn } from "@evoloop/shared/lib/utils"
import { Circle, Loader2, Mic, Pause, Volume2 } from "lucide-react"
import { useTranslation } from "react-i18next"
import type { VoiceState } from "@/stores/voiceStore"
import { useVoiceStore } from "@/stores/voiceStore"

const stateConfig: Record<
  VoiceState,
  { icon: React.ReactNode; labelKey: string; color: string; animate: boolean }
> = {
  idle: {
    icon: <Circle className="h-3 w-3" />,
    labelKey: "voice.state.idle",
    color: "text-muted-foreground",
    animate: false,
  },
  listening: {
    icon: <Mic className="h-3 w-3" />,
    labelKey: "voice.state.listening",
    color: "text-green-500",
    animate: true,
  },
  processing: {
    icon: <Loader2 className="h-3 w-3" />,
    labelKey: "voice.state.processing",
    color: "text-yellow-500",
    animate: true,
  },
  speaking: {
    icon: <Volume2 className="h-3 w-3" />,
    labelKey: "voice.state.speaking",
    color: "text-blue-500",
    animate: true,
  },
  interrupted: {
    icon: <Pause className="h-3 w-3" />,
    labelKey: "voice.state.interrupted",
    color: "text-orange-500",
    animate: false,
  },
}

export function VoiceStateIndicator() {
  const { t } = useTranslation()
  const voiceState = useVoiceStore((s) => s.voiceState)
  const partialText = useVoiceStore((s) => s.partialText)
  const tokenBuffer = useVoiceStore((s) => s.tokenBuffer)
  const ttsSentence = useVoiceStore((s) => s.ttsSentence)

  if (voiceState === "idle") return null

  const cfg = stateConfig[voiceState]

  return (
    <div
      className={cn(
        "fixed bottom-4 right-4 z-50 flex items-center gap-2 rounded-full border bg-background px-3 py-1.5 shadow-lg",
        cfg.animate && "animate-pulse",
      )}
    >
      <span className={cfg.color}>{cfg.icon}</span>
      <span className="text-xs font-medium">{t(cfg.labelKey)}</span>
      {voiceState === "listening" && partialText && (
        <span className="max-w-[200px] truncate text-xs text-muted-foreground">
          {partialText}
        </span>
      )}
      {voiceState === "speaking" && ttsSentence && (
        <span className="max-w-[200px] truncate text-xs text-muted-foreground">
          {ttsSentence}
        </span>
      )}
      {voiceState === "speaking" && tokenBuffer && (
        <span className="max-w-[200px] truncate text-xs text-muted-foreground">
          {tokenBuffer.slice(-120)}
        </span>
      )}
    </div>
  )
}
