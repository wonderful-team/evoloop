import {cn} from "@evoloop/shared/lib/utils"
import {AlertCircle} from "lucide-react"
import {memo} from "react"
import {useTranslation} from "react-i18next"
import {HITL_STATUS} from "@/stores/agent/hitlConstants"
import {useAgentStore} from "@/stores/agentStore"

/**
 * HITLBanner - Global banner when Agent is waiting for human input
 * Shows at the top of the chat area with a pulsing animation
 */
export const HITLBanner = memo(() => {
  const { t } = useTranslation()
  const status = useAgentStore((s) => s.status)
  const humanRequest = useAgentStore((s) => s.humanRequest)

  // Only show when interrupted with a human request
  const isVisible = status === HITL_STATUS.interrupted && humanRequest !== null

  if (!isVisible) return null

  return (
    <div
      className={cn(
        "flex items-center justify-center gap-2 px-4 py-2",
        "bg-warning/10 border-b border-warning/20",
        "animate-pulse",
      )}
    >
      <AlertCircle size={16} className="text-warning shrink-0" />
      <span className="text-sm font-medium text-warning">
        {t("chat.hitl.waiting")}
      </span>
    </div>
  )
})

HITLBanner.displayName = "HITLBanner"
