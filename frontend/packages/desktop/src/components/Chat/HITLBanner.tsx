import { cn } from "@evoloop/shared/lib/utils"
import { AlertCircle } from "lucide-react"
import { memo } from "react"
import { useTranslation } from "react-i18next"
import { useAgentStore } from "@/stores/agentStore"

/**
 * HITLBanner - Global banner when Agent is waiting for human input
 * Shows at the top of the chat area with a pulsing animation
 */
export const HITLBanner = memo(() => {
  const { t } = useTranslation()
  const status = useAgentStore((s) => s.status)
  const humanRequest = useAgentStore((s) => s.humanRequest)

  // Only show when interrupted with a human request
  const isVisible = status === "interrupted" && humanRequest !== null

  if (!isVisible) return null

  return (
    <div
      className={cn(
        "flex items-center justify-center gap-2 px-4 py-2",
        "bg-amber-500/10 border-b border-amber-500/20",
        "animate-pulse",
      )}
    >
      <AlertCircle
        size={16}
        className="text-amber-600 dark:text-amber-400 shrink-0"
      />
      <span className="text-sm font-medium text-amber-700 dark:text-amber-400">
        {t("chat.hitl.waiting")}
      </span>
    </div>
  )
})

HITLBanner.displayName = "HITLBanner"
