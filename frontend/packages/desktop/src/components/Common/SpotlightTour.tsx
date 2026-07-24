import { Button } from "@evoloop/shared/components/ui/button"
import { AnimatePresence, motion } from "framer-motion"
import { ChevronLeft, ChevronRight, X } from "lucide-react"
import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
} from "react"
import { useTranslation } from "react-i18next"

// =====================
// Types
// =====================
export interface TourStep {
  /** CSS selector for target element (e.g., '[data-tour="sidebar-chat"]') */
  target: string
  /** i18n key for title */
  titleKey: string
  /** i18n key for description */
  contentKey: string
  /** Tooltip placement */
  placement?: "top" | "bottom" | "left" | "right"
  /** Extra padding around spotlight */
  spotlightPadding?: number
  /** Optional action when this step is shown */
  onShow?: () => void
}

interface TourContextValue {
  isActive: boolean
  currentStep: number
  steps: TourStep[]
  startTour: () => void
  endTour: (completed?: boolean) => void
  nextStep: () => void
  prevStep: () => void
  skipTour: () => void
}

// =====================
// Context
// =====================
const TourContext = createContext<TourContextValue | null>(null)

export function useTour() {
  const ctx = useContext(TourContext)
  if (!ctx) throw new Error("useTour must be used within SpotlightTourProvider")
  return ctx
}

// =====================
// Provider
// =====================
interface SpotlightTourProviderProps {
  children: React.ReactNode
  steps: TourStep[]
  storageKey?: string
  onComplete?: () => void
  onSkip?: () => void
  preventAutoStart?: boolean
}

const STORAGE_KEY_DEFAULT = "evoloop_desktop_tour_seen"

export function SpotlightTourProvider({
  children,
  steps,
  storageKey = STORAGE_KEY_DEFAULT,
  onComplete,
  onSkip,
  preventAutoStart = false,
}: SpotlightTourProviderProps) {
  const [isActive, setIsActive] = useState(false)
  const [currentStep, setCurrentStep] = useState(0)

  // Check if tour was already seen
  useEffect(() => {
    if (preventAutoStart) return

    const seen = localStorage.getItem(storageKey)
    if (!seen) {
      // Delay tour start to let elements render
      const timer = setTimeout(() => setIsActive(true), 800)
      return () => clearTimeout(timer)
    }
  }, [storageKey, preventAutoStart])

  const startTour = useCallback(() => {
    setCurrentStep(0)
    setIsActive(true)
  }, [])

  const endTour = useCallback(
    (completed = false) => {
      setIsActive(false)
      localStorage.setItem(storageKey, "true")
      if (completed) {
        onComplete?.()
      }
    },
    [storageKey, onComplete],
  )

  const skipTour = useCallback(() => {
    setIsActive(false)
    localStorage.setItem(storageKey, "true")
    onSkip?.()
  }, [storageKey, onSkip])

  const nextStep = useCallback(() => {
    if (currentStep < steps.length - 1) {
      setCurrentStep((s) => s + 1)
    } else {
      endTour(true)
    }
  }, [currentStep, steps.length, endTour])

  const prevStep = useCallback(() => {
    if (currentStep > 0) {
      setCurrentStep((s) => s - 1)
    }
  }, [currentStep])

  const value = useMemo(
    () => ({
      isActive,
      currentStep,
      steps,
      startTour,
      endTour,
      nextStep,
      prevStep,
      skipTour,
    }),
    [
      isActive,
      currentStep,
      steps,
      startTour,
      endTour,
      nextStep,
      prevStep,
      skipTour,
    ],
  )

  return (
    <TourContext.Provider value={value}>
      {children}
      <AnimatePresence>{isActive && <SpotlightOverlay />}</AnimatePresence>
    </TourContext.Provider>
  )
}

// =====================
// Spotlight Overlay
// =====================
function SpotlightOverlay() {
  const { t } = useTranslation()
  const { currentStep, steps, nextStep, prevStep, skipTour } = useTour()
  const step = steps[currentStep]

  const [targetRect, setTargetRect] = useState<DOMRect | null>(null)
  const [tooltipPosition, setTooltipPosition] = useState({ top: 0, left: 0 })

  // Find target element and calculate position
  useEffect(() => {
    const findTarget = () => {
      const el = document.querySelector(step.target)
      if (el) {
        const rect = el.getBoundingClientRect()
        setTargetRect(rect)

        // Calculate tooltip position
        const padding = step.spotlightPadding ?? 8
        const tooltipWidth = 340
        const tooltipHeight = 180
        const offset = 16

        let top = 0
        let left = 0

        const placement = step.placement ?? "bottom"

        switch (placement) {
          case "top":
            top = rect.top - tooltipHeight - offset
            left = rect.left + rect.width / 2 - tooltipWidth / 2
            break
          case "bottom":
            top = rect.bottom + offset + padding
            left = rect.left + rect.width / 2 - tooltipWidth / 2
            break
          case "left":
            top = rect.top + rect.height / 2 - tooltipHeight / 2
            left = rect.left - tooltipWidth - offset
            break
          case "right":
            top = rect.top + rect.height / 2 - tooltipHeight / 2
            left = rect.right + offset + padding
            break
        }

        // Keep within viewport
        left = Math.max(
          16,
          Math.min(left, window.innerWidth - tooltipWidth - 16),
        )
        top = Math.max(
          16,
          Math.min(top, window.innerHeight - tooltipHeight - 16),
        )

        setTooltipPosition({ top, left })

        // Fire onShow callback
        step.onShow?.()
      }
    }

    // Initial find + resize observer
    findTarget()
    const resizeObserver = new ResizeObserver(findTarget)
    const target = document.querySelector(step.target)
    if (target) resizeObserver.observe(target)

    window.addEventListener("resize", findTarget)
    return () => {
      window.removeEventListener("resize", findTarget)
      resizeObserver.disconnect()
    }
  }, [step])

  const padding = step.spotlightPadding ?? 8

  return (
    <motion.div
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      exit={{ opacity: 0 }}
      className="fixed inset-0 z-[9999] pointer-events-auto"
      onClick={(e) => {
        // Don't close on clicking the spotlight area
        if (targetRect) {
          const x = e.clientX
          const y = e.clientY
          const inSpotlight =
            x >= targetRect.left - padding &&
            x <= targetRect.right + padding &&
            y >= targetRect.top - padding &&
            y <= targetRect.bottom + padding
          if (inSpotlight) return
        }
      }}
    >
      {/* Dark overlay with cutout */}
      <svg
        className="absolute inset-0 w-full h-full"
        style={{ pointerEvents: "none" }}
      >
        <defs>
          <mask id="spotlight-mask">
            <rect x="0" y="0" width="100%" height="100%" fill="white" />
            {targetRect && (
              <rect
                x={targetRect.left - padding}
                y={targetRect.top - padding}
                width={targetRect.width + padding * 2}
                height={targetRect.height + padding * 2}
                rx="8"
                fill="black"
              />
            )}
          </mask>
        </defs>
        <rect
          x="0"
          y="0"
          width="100%"
          height="100%"
          fill="rgba(0,0,0,0.6)"
          mask="url(#spotlight-mask)"
        />
      </svg>

      {/* Spotlight border glow */}
      {targetRect && (
        <motion.div
          initial={{ opacity: 0, scale: 0.95 }}
          animate={{ opacity: 1, scale: 1 }}
          className="absolute border-2 border-primary rounded-lg shadow-lg shadow-primary/30 pointer-events-none"
          style={{
            top: targetRect.top - padding,
            left: targetRect.left - padding,
            width: targetRect.width + padding * 2,
            height: targetRect.height + padding * 2,
          }}
        />
      )}

      {/* Tooltip Card */}
      <motion.div
        initial={{ opacity: 0, y: 10 }}
        animate={{ opacity: 1, y: 0 }}
        exit={{ opacity: 0, y: 10 }}
        transition={{ delay: 0.1 }}
        className="absolute bg-popover border border-border rounded-xl shadow-2xl p-5 w-[340px] pointer-events-auto"
        style={{
          top: tooltipPosition.top,
          left: tooltipPosition.left,
        }}
      >
        {/* Skip button */}
        <button
          onClick={skipTour}
          className="absolute top-3 right-3 text-muted-foreground hover:text-foreground transition-colors"
          aria-label={t("tour.skipAriaLabel")}
        >
          <X size={16} />
        </button>

        {/* Content */}
        <div className="pr-6">
          <h3 className="font-semibold text-lg text-foreground mb-2">
            {t(step.titleKey)}
          </h3>
          <p className="text-sm text-muted-foreground leading-relaxed">
            {t(step.contentKey)}
          </p>
        </div>

        {/* Footer */}
        <div className="flex items-center justify-between mt-5 pt-4 border-t border-border/50">
          {/* Progress */}
          <div className="flex items-center gap-1.5">
            {steps.map((_, i) => (
              <div
                key={i}
                className={`h-1.5 rounded-full transition-all ${
                  i === currentStep
                    ? "w-4 bg-primary"
                    : i < currentStep
                      ? "w-1.5 bg-primary/60"
                      : "w-1.5 bg-muted"
                }`}
              />
            ))}
          </div>

          {/* Navigation */}
          <div className="flex items-center gap-2">
            {currentStep > 0 && (
              <Button
                variant="ghost"
                size="sm"
                onClick={prevStep}
                className="h-8 px-3"
              >
                <ChevronLeft size={14} className="mr-1" />
                {t("tour.prev")}
              </Button>
            )}
            <Button size="sm" onClick={nextStep} className="h-8 px-4 shadow-sm">
              {currentStep === steps.length - 1
                ? t("tour.finish")
                : t("tour.next")}
              {currentStep < steps.length - 1 && (
                <ChevronRight size={14} className="ml-1" />
              )}
            </Button>
          </div>
        </div>
      </motion.div>
    </motion.div>
  )
}

// =====================
// Exports
// =====================
export { SpotlightOverlay }
