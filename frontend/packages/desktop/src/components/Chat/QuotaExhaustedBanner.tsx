import {cn} from "@evoloop/shared/lib/utils"
import {AlertTriangle} from "lucide-react"
import {memo} from "react"
import {useTranslation} from "react-i18next"
import {useAgentStore} from "@/stores/agentStore"

/**
 * QuotaExhaustedBanner - Global banner when LLM quota is exhausted
 * Shows at the top of the chat area with a pulsing animation
 * Similar to HITLBanner but for quota exhaustion
 */
export const QuotaExhaustedBanner = memo(() => {
  const { t } = useTranslation()
  const status = useAgentStore((s) => s.status)
  const quotaInfo = useAgentStore((s) => s.quotaExhaustedInfo)

  // Only show when quota is exhausted
  const isVisible = status === "quota_exhausted"

  if (!isVisible) return null

  return (
    <div
      className={cn(
        "flex items-center justify-center gap-2 px-4 py-2",
        "bg-destructive/10 border-b border-destructive/20",
        "animate-pulse",
      )}
    >
      <AlertTriangle size={16} className="text-destructive shrink-0" />
      <span className="text-sm font-medium text-destructive">
        {quotaInfo?.title || t("chat.quota.banner.title")}
      </span>
      <span className="text-sm text-destructive/80">
        - {quotaInfo?.message || t("chat.quota.banner.message")}
      </span>
    </div>
  )
})

QuotaExhaustedBanner.displayName = "QuotaExhaustedBanner"
