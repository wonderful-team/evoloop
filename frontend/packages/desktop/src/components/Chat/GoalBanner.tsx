import { AnimatePresence, motion } from "framer-motion"
import { Target } from "lucide-react"
import { memo } from "react"
import { useTranslation } from "react-i18next"
import { useChatStore } from "@/stores/chatStore"

export const GoalBanner = memo(() => {
  const { t } = useTranslation()
  const sessionGoal = useChatStore((s) => s.sessionGoal)

  if (!sessionGoal) return null

  return (
    <AnimatePresence>
      <motion.div
        initial={{ opacity: 0, y: -10 }}
        animate={{ opacity: 1, y: 0 }}
        exit={{ opacity: 0, y: -10 }}
        className="mb-8 px-4"
      >
        <div className="bg-muted/30 border border-border/50 rounded-xl p-4 flex gap-4 items-start shadow-sm hover:shadow-md transition-shadow">
          <div className="mt-0.5 bg-primary/10 p-2 rounded-lg shrink-0">
            <Target className="w-5 h-5 text-primary" />
          </div>
          <div className="flex-1 min-w-0">
            <h4 className="text-xs font-bold text-muted-foreground uppercase tracking-wider mb-1">
              {t("chat.goalBanner.title")}
            </h4>
            <p className="text-sm text-foreground leading-relaxed font-medium">
              {sessionGoal}
            </p>
          </div>
        </div>
      </motion.div>
    </AnimatePresence>
  )
})

GoalBanner.displayName = "GoalBanner"
