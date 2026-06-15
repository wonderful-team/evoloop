import { AlertTriangle } from "lucide-react"
import { memo } from "react"
import { useTranslation } from "react-i18next"
import { useChatStore } from "@/stores/chatStore"
import { cn } from "@evoloop/shared/lib/utils"

/**
 * QuotaExhaustedBanner - Global banner when LLM quota is exhausted
 * Shows at the top of the chat area with a pulsing animation
 * Similar to HITLBanner but for quota exhaustion
 */
export const QuotaExhaustedBanner = memo(() => {
    const { t } = useTranslation()
    const status = useChatStore((s) => s.status)
    const quotaInfo = useChatStore((s) => s.quotaExhaustedInfo)

    // Only show when quota is exhausted
    const isVisible = status === "quota_exhausted"

    if (!isVisible) return null

    return (
        <div
            className={cn(
                "flex items-center justify-center gap-2 px-4 py-2",
                "bg-red-500/10 border-b border-red-500/20",
                "animate-pulse"
            )}
        >
            <AlertTriangle size={16} className="text-red-600 dark:text-red-400 shrink-0" />
            <span className="text-sm font-medium text-red-700 dark:text-red-400">
                {quotaInfo?.title || t("chat.quota.banner.title")}
            </span>
            <span className="text-sm text-red-600/80 dark:text-red-400/80">
                - {quotaInfo?.message || t("chat.quota.banner.message")}
            </span>
        </div>
    )
})

QuotaExhaustedBanner.displayName = "QuotaExhaustedBanner"
