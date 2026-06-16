import { Button } from "@evoloop/shared/components/ui/button"
import { motion } from "framer-motion"
import { CheckCircle, FolderOpen, MessageSquare, Sparkles } from "lucide-react"
import { useEffect } from "react"
import { useTranslation } from "react-i18next"
import { useWizard } from "../WizardContext"

export function CompletionStep() {
  const { t } = useTranslation()
  const { nextStep, setCanProceed } = useWizard()

  useEffect(() => {
    setCanProceed(true)
  }, [setCanProceed])

  const features = [
    { icon: MessageSquare, key: "chat" },
    { icon: FolderOpen, key: "projects" },
    { icon: Sparkles, key: "ai" },
  ]

  return (
    <motion.div
      initial={{ opacity: 0, scale: 0.95 }}
      animate={{ opacity: 1, scale: 1 }}
      exit={{ opacity: 0, scale: 0.95 }}
      className="flex flex-col items-center justify-center text-center py-12 px-8"
    >
      {/* Success Icon */}
      <motion.div
        initial={{ scale: 0 }}
        animate={{ scale: 1 }}
        transition={{ delay: 0.1, type: "spring", stiffness: 200 }}
        className="mb-6"
      >
        <div className="w-20 h-20 rounded-full bg-green-100 dark:bg-green-900/30 flex items-center justify-center">
          <CheckCircle className="w-10 h-10 text-green-600 dark:text-green-400" />
        </div>
      </motion.div>

      {/* Title */}
      <motion.h1
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        transition={{ delay: 0.2 }}
        className="text-2xl font-bold tracking-tight mb-3"
      >
        {t("wizard.completion.title")}
      </motion.h1>

      {/* Subtitle */}
      <motion.p
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        transition={{ delay: 0.3 }}
        className="text-muted-foreground max-w-md mb-8"
      >
        {t("wizard.completion.subtitle")}
      </motion.p>

      {/* Feature Cards */}
      <motion.div
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        transition={{ delay: 0.4 }}
        className="grid grid-cols-3 gap-4 mb-10 w-full max-w-md"
      >
        {features.map(({ icon: Icon, key }) => (
          <div
            key={key}
            className="flex flex-col items-center gap-2 p-4 rounded-lg bg-muted/50"
          >
            <Icon className="w-6 h-6 text-primary" />
            <span className="text-xs text-muted-foreground">
              {t(`wizard.completion.${key}`)}
            </span>
          </div>
        ))}
      </motion.div>

      {/* CTA Button */}
      <motion.div
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        transition={{ delay: 0.5 }}
      >
        <Button size="lg" onClick={nextStep} className="px-10">
          {t("wizard.completion.start")}
        </Button>
      </motion.div>
    </motion.div>
  )
}
