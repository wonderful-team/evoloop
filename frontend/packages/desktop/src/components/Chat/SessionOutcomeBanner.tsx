import { CheckCircle2, XCircle, AlertCircle, Sparkles } from "lucide-react"
import { useTranslation } from "react-i18next"
import { motion, AnimatePresence } from "framer-motion"

interface SessionOutcomeBannerProps {
  outcome: string | null
}

export function SessionOutcomeBanner({ outcome }: SessionOutcomeBannerProps) {
  const { t } = useTranslation()

  if (!outcome || outcome === "") return null

  const config = {
    SUCCESS: {
      bg: "bg-green-500/10",
      border: "border-green-500/20",
      icon: <CheckCircle2 className="w-5 h-5 text-green-500" />,
      text: "text-green-600 dark:text-green-400",
      label: t("chat.outcome.success", "Mission Accomplished"),
      desc: t("chat.outcome.successDesc", "The session has concluded successfully. All goals have been met.")
    },
    FAILED: {
      bg: "bg-red-500/10",
      border: "border-red-500/20",
      icon: <XCircle className="w-5 h-5 text-red-500" />,
      text: "text-red-600 dark:text-red-400",
      label: t("chat.outcome.failed", "Mission Failed"),
      desc: t("chat.outcome.failedDesc", "The agent was unable to complete the request. Check the summary for reasons.")
    },
    INCOMPLETE: {
      bg: "bg-amber-500/10",
      border: "border-amber-500/20",
      icon: <AlertCircle className="w-5 h-5 text-amber-500" />,
      text: "text-amber-600 dark:text-amber-400",
      label: t("chat.outcome.incomplete", "Partially Complete"),
      desc: t("chat.outcome.incompleteDesc", "Some tasks remain. The session ended with partial results.")
    }
  }[outcome as "SUCCESS" | "FAILED" | "INCOMPLETE"] || {
    bg: "bg-muted/30",
    border: "border-border",
    icon: <Sparkles className="w-5 h-5 text-muted-foreground" />,
    text: "text-muted-foreground",
    label: t("chat.outcome.finished", "Session Concluded"),
    desc: t("chat.outcome.finishedDesc", "The agent has finished the review process.")
  }

  return (
    <AnimatePresence>
      <motion.div
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        exit={{ opacity: 0, scale: 0.95 }}
        className={`mx-4 mb-6 p-4 rounded-xl border ${config.bg} ${config.border} flex gap-4 items-start shadow-sm backdrop-blur-sm overflow-hidden relative group`}
      >
        <div className="shrink-0 mt-0.5">
           {config.icon}
        </div>
        <div className="flex flex-col gap-0.5 relative z-10">
          <span className={`text-sm font-semibold tracking-tight ${config.text}`}>
            {config.label}
          </span>
          <span className="text-xs text-muted-foreground/80 leading-relaxed max-w-lg">
            {config.desc}
          </span>
        </div>
        
        {/* Subtle decorative glow */}
        <div className={`absolute -right-8 -top-8 w-32 h-32 rounded-full blur-3xl opacity-10 ${config.bg.replace('/10', '/30')}`} />
      </motion.div>
    </AnimatePresence>
  )
}
