import {
  createContext,
  useCallback,
  useContext,
  useMemo,
  useState,
} from "react"

// =====================
// Types
// =====================
export interface WizardData {
  // LLM Configuration
  defaultModelId: string // preset model id or "custom"
  selectedModelId: string // for provider config template
  llmProvider: string
  llmBaseUrl: string
  llmModel: string
  llmVisionModel: string
  llmApiKey: string
  // Workspace
  workspaceRoot: string
  // Status
  llmTested: boolean
}

interface WizardContextValue {
  currentStep: number
  totalSteps: number
  data: WizardData
  setData: (updates: Partial<WizardData>) => void
  nextStep: () => void
  prevStep: () => void
  goToStep: (step: number) => void
  isFirstStep: boolean
  isLastStep: boolean
  canProceed: boolean
  setCanProceed: (can: boolean) => void
}

// =====================
// Context
// =====================
const WizardContext = createContext<WizardContextValue | null>(null)

export function useWizard() {
  const ctx = useContext(WizardContext)
  if (!ctx) throw new Error("useWizard must be used within WizardProvider")
  return ctx
}

// =====================
// Provider
// =====================
interface WizardProviderProps {
  children: React.ReactNode
  totalSteps: number
  onComplete: (data: WizardData) => void
}

const defaultData: WizardData = {
  defaultModelId: "",
  selectedModelId: "",
  llmProvider: "openai",
  llmBaseUrl: "",
  llmModel: "",
  llmVisionModel: "",
  llmApiKey: "",
  workspaceRoot: "",
  llmTested: false,
}

export function WizardProvider({
  children,
  totalSteps,
  onComplete,
}: WizardProviderProps) {
  const [currentStep, setCurrentStep] = useState(0)
  const [data, setDataState] = useState<WizardData>(defaultData)
  const [canProceed, setCanProceed] = useState(false)

  const setData = useCallback((updates: Partial<WizardData>) => {
    setDataState((prev) => ({ ...prev, ...updates }))
  }, [])

  const nextStep = useCallback(() => {
    if (currentStep < totalSteps - 1) {
      setCurrentStep((s) => s + 1)
      setCanProceed(false) // Reset for next step
    } else {
      // Last step - complete
      onComplete(data)
    }
  }, [currentStep, totalSteps, data, onComplete])

  const prevStep = useCallback(() => {
    if (currentStep > 0) {
      setCurrentStep((s) => s - 1)
    }
  }, [currentStep])

  const goToStep = useCallback(
    (step: number) => {
      if (step >= 0 && step < totalSteps) {
        setCurrentStep(step)
      }
    },
    [totalSteps],
  )

  const value = useMemo(
    () => ({
      currentStep,
      totalSteps,
      data,
      setData,
      nextStep,
      prevStep,
      goToStep,
      isFirstStep: currentStep === 0,
      isLastStep: currentStep === totalSteps - 1,
      canProceed,
      setCanProceed,
    }),
    [
      currentStep,
      totalSteps,
      data,
      setData,
      nextStep,
      prevStep,
      goToStep,
      canProceed,
    ],
  )

  return (
    <WizardContext.Provider value={value}>{children}</WizardContext.Provider>
  )
}
