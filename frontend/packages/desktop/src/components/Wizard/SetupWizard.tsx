import { Button } from "@evoloop/shared/components/ui/button"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@evoloop/shared/components/ui/dialog"
import { useQuery, useQueryClient } from "@tanstack/react-query"
import { AnimatePresence } from "framer-motion"
import { ChevronLeft, ChevronRight } from "lucide-react"
import { useCallback, useMemo } from "react"
import { useTranslation } from "react-i18next"
import { toast } from "sonner"
import { SystemService } from "@/client"
import { useTour } from "@/components/Common/SpotlightTour"
import { needsLlmStepForConfig } from "./llmConfig"
import { CompletionStep } from "./steps/CompletionStep"
import { LLMConfigStep } from "./steps/LLMConfigStep"
import { ProjectsStep } from "./steps/ProjectsStep"
import { WelcomeStep } from "./steps/WelcomeStep"
import { markSetupCompleted } from "./useSetupRequired"
import { useWizard, type WizardData, WizardProvider } from "./WizardContext"

// =====================
// Step Components Map
// =====================
const ALL_STEPS = [
  { key: "welcome", component: WelcomeStep },
  { key: "llm", component: LLMConfigStep },
  { key: "projects", component: ProjectsStep },
  { key: "completion", component: CompletionStep },
]

const PLATFORM_STEPS = ALL_STEPS.filter((step) => step.key !== "llm")

// =====================
// Wizard Content
// =====================
function WizardContent({ currentSteps }: { currentSteps: typeof ALL_STEPS }) {
  const { t } = useTranslation()
  const {
    currentStep,
    totalSteps,
    nextStep,
    prevStep,
    isFirstStep,
    isLastStep,
    canProceed,
  } = useWizard()

  const CurrentStepComponent = currentSteps[currentStep]?.component

  return (
    <div className="flex flex-col h-full">
      {/* Progress Bar */}
      <div className="px-6 pt-4">
        <div className="flex items-center gap-2">
          {currentSteps.map((step, i) => (
            <div
              key={step.key}
              className={`h-1.5 flex-1 rounded-full transition-colors ${
                i <= currentStep ? "bg-primary" : "bg-muted"
              }`}
            />
          ))}
        </div>
        <p className="text-xs text-muted-foreground text-center mt-2">
          {t("wizard.stepOf", { current: currentStep + 1, total: totalSteps })}
        </p>
      </div>

      {/* Step Content */}
      <div className="flex-1 overflow-auto">
        <AnimatePresence mode="wait">
          {CurrentStepComponent && (
            <CurrentStepComponent key={currentSteps[currentStep].key} />
          )}
        </AnimatePresence>
      </div>

      {/* Navigation Footer */}
      {!isFirstStep && !isLastStep && (
        <div className="px-6 pb-6 pt-4 border-t flex items-center justify-between">
          <Button variant="ghost" onClick={prevStep} disabled={isFirstStep}>
            <ChevronLeft className="w-4 h-4 mr-1" />
            {t("wizard.prev")}
          </Button>

          <Button onClick={nextStep} disabled={!canProceed}>
            {t("wizard.next")}
            <ChevronRight className="w-4 h-4 ml-1" />
          </Button>
        </div>
      )}
    </div>
  )
}

// =====================
// Main Wizard Component
// =====================
interface SetupWizardProps {
  open: boolean
  onOpenChange: (open: boolean) => void
}

export function SetupWizard({ open, onOpenChange }: SetupWizardProps) {
  const { t } = useTranslation()
  const queryClient = useQueryClient()
  const { startTour } = useTour()

  // Determine whether the LLM step is required: platform mode routes through
  // the EvoLoop Gateway and has no default-model choice to make.
  const { data: config } = useQuery({
    queryKey: ["systemConfig"],
    queryFn: () => SystemService.getSystemConfig(),
    enabled: open,
    staleTime: 1000 * 60 * 5,
  })

  const configMap: Record<string, string> = useMemo(() => {
    const map: Record<string, string> = {}
    if (Array.isArray(config)) {
      ;(config as unknown as Array<{ key: string; value: string }>).forEach(
        (item) => {
          map[item.key] = item.value
        },
      )
    }
    return map
  }, [config])

  const needsLlmStep = useMemo(
    () => needsLlmStepForConfig(configMap),
    [configMap],
  )

  const currentSteps = needsLlmStep ? ALL_STEPS : PLATFORM_STEPS

  const handleComplete = useCallback(
    async (data: WizardData) => {
      try {
        // Save LLM Configuration (only when the LLM step was shown)
        if (needsLlmStep) {
          await SystemService.applyLlmConfig({
            requestBody: {
              provider: data.llmProvider,
              base_url: data.llmBaseUrl,
              model: data.llmModel,
              vision_model: data.llmVisionModel || data.llmModel,
              api_key: data.llmApiKey,
            },
          })
        }

        // Save Workspace Root
        await SystemService.updateSystemConfig({
          requestBody: { key: "WORKSPACE_ROOT", value: data.workspaceRoot },
        })

        // Mark setup as completed
        markSetupCompleted()

        // Invalidate config cache
        await queryClient.invalidateQueries({ queryKey: ["systemConfig"] })

        toast.success(t("wizard.saveSuccess"))

        // Close wizard
        onOpenChange(false)

        // Trigger product tour after a short delay
        setTimeout(() => {
          startTour()
        }, 500)
      } catch (error) {
        toast.error(
          t("wizard.saveErrorWithMessage", {
            message: t("wizard.saveError"),
            detail: (error as Error).message,
          }),
        )
      }
    },
    [queryClient, onOpenChange, startTour, t, needsLlmStep],
  )

  const totalSteps = currentSteps.length

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent
        className="max-w-xl p-0 overflow-hidden"
        showCloseButton={false}
      >
        <DialogHeader className="sr-only">
          <DialogTitle>{t("wizard.title")}</DialogTitle>
          <DialogDescription>{t("wizard.description")}</DialogDescription>
        </DialogHeader>

        <WizardProvider totalSteps={totalSteps} onComplete={handleComplete}>
          <WizardContent currentSteps={currentSteps} />
        </WizardProvider>
      </DialogContent>
    </Dialog>
  )
}

export default SetupWizard
