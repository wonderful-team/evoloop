import {Button} from "@evoloop/shared/components/ui/button"
import {cn} from "@evoloop/shared/lib/utils"
import {Loader2, Pause, Volume2} from "lucide-react"
import {useTranslation} from "react-i18next"
import {useTTS} from "@/hooks/useTTS"

interface TTSButtonProps {
  text: string
  className?: string
  size?: "sm" | "md" | "lg"
  variant?: "ghost" | "secondary" | "outline"
}

// TTSButton - 语音朗读按钮
// 注意：前端不做权限控制，后端返回 403 时会由拦截器处理并显示升级提示
export function TTSButton({
  text,
  className,
  size = "sm",
  variant = "ghost",
}: TTSButtonProps) {
  const { t } = useTranslation()
  const { isSpeaking, isLoading, speak, stop } = useTTS()

  const handleClick = () => {
    if (isSpeaking) {
      stop()
    } else {
      speak(text)
    }
  }

  const sizeClasses = {
    sm: "h-6 w-6",
    md: "h-8 w-8",
    lg: "h-10 w-10",
  }

  const iconSizes = {
    sm: "h-3 w-3",
    md: "h-4 w-4",
    lg: "h-5 w-5",
  }

  return (
    <Button
      variant={variant}
      size="icon"
      className={cn(sizeClasses[size], className)}
      onClick={handleClick}
      title={isSpeaking ? t("chat.tts.stop") : t("chat.tts.speak")}
    >
      {isLoading ? (
        <Loader2 className={cn(iconSizes[size], "animate-spin")} />
      ) : isSpeaking ? (
        <Pause className={iconSizes[size]} />
      ) : (
        <Volume2 className={iconSizes[size]} />
      )}
    </Button>
  )
}
