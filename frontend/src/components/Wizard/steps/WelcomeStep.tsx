import { motion } from "framer-motion"
import { Rocket } from "lucide-react"
import { useEffect } from "react"
import { useTranslation } from "react-i18next"
import { Button } from "@/components/ui/button"
import { useWizard } from "../WizardContext"

export function WelcomeStep() {
    const { t } = useTranslation()
    const { nextStep, setCanProceed } = useWizard()

    useEffect(() => {
        setCanProceed(true)
    }, [setCanProceed])

    return (
        <motion.div
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -20 }}
            className="flex flex-col items-center justify-center text-center py-12 px-8"
        >
            {/* Logo / Icon */}
            <motion.div
                initial={{ scale: 0 }}
                animate={{ scale: 1 }}
                transition={{ delay: 0.2, type: "spring", stiffness: 200 }}
                className="mb-8"
            >
                <div className="w-24 h-24 rounded-full bg-gradient-to-br from-primary/20 to-primary/5 flex items-center justify-center">
                    <Rocket className="w-12 h-12 text-primary" />
                </div>
            </motion.div>

            {/* Title */}
            <motion.h1
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                transition={{ delay: 0.3 }}
                className="text-3xl font-bold tracking-tight mb-4"
            >
                {t("wizard.welcome.title")}
            </motion.h1>

            {/* Subtitle */}
            <motion.p
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                transition={{ delay: 0.4 }}
                className="text-lg text-muted-foreground max-w-md mb-8"
            >
                {t("wizard.welcome.subtitle")}
            </motion.p>

            {/* Features list */}
            <motion.div
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                transition={{ delay: 0.5 }}
                className="flex flex-col gap-3 mb-10 text-left"
            >
                {["feature1", "feature2", "feature3"].map((key, i) => (
                    <div key={key} className="flex items-center gap-3">
                        <div className="w-6 h-6 rounded-full bg-primary/10 flex items-center justify-center text-primary text-sm font-medium">
                            {i + 1}
                        </div>
                        <span className="text-muted-foreground">
                            {t(`wizard.welcome.${key}`)}
                        </span>
                    </div>
                ))}
            </motion.div>

            {/* CTA Button */}
            <motion.div
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                transition={{ delay: 0.6 }}
            >
                <Button size="lg" onClick={nextStep} className="px-8">
                    {t("wizard.welcome.start")}
                </Button>
            </motion.div>
        </motion.div>
    )
}
