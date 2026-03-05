/**
 * SynthesisProgress - Display synthesis progress with animated indicators
 */

import { useTranslation } from "react-i18next"
import { Loader2, CheckCircle2, Circle, AlertCircle } from "lucide-react"
import { cn } from "@evoloop/shared/lib/utils"

interface SynthesisProgressProps {
    status: string
    progress: number
    phase: string
}

const phaseIds = [
    "loadingData",
    "extractingKeyframes",
    "analyzingFrames",
    "understandingPhases",
    "identifyingSteps",
    "generatingMacro",
    "generatingMetadata",
    "completed",
]

export function SynthesisProgress({ status, progress, phase }: SynthesisProgressProps) {
    const { t } = useTranslation()
    const currentPhaseIndex = phaseIds.findIndex((id) => phase.includes(id.toLowerCase()) || id.toLowerCase() === phase)

    return (
        <div className="w-full max-w-md space-y-4">
            {/* Progress bar */}
            <div className="relative h-2 bg-muted rounded-full overflow-hidden">
                <div
                    className={cn(
                        "absolute left-0 top-0 bottom-0 transition-all duration-500",
                        status === "failed" ? "bg-destructive" : "bg-primary"
                    )}
                    style={{ width: `${progress}%` }}
                />
            </div>

            {/* Progress text */}
            <div className="text-center">
                <p className="text-2xl font-bold">{progress}%</p>
                <p className="text-sm text-muted-foreground capitalize">{phase.replace(/_/g, " ")}</p>
            </div>

            {/* Phase indicators */}
            <div className="space-y-1">
                {phaseIds.map((id, idx) => {
                    const isCompleted = idx < currentPhaseIndex
                    const isCurrent = idx === currentPhaseIndex
                    const isPending = idx > currentPhaseIndex

                    return (
                        <div
                            key={id}
                            className={cn(
                                "flex items-center gap-2 text-sm transition-opacity",
                                isPending && "opacity-30"
                            )}
                        >
                            {isCompleted ? (
                                <CheckCircle2 className="h-4 w-4 text-green-500" />
                            ) : isCurrent ? (
                                <Loader2 className="h-4 w-4 animate-spin text-primary" />
                            ) : (
                                <Circle className="h-4 w-4 text-muted-foreground" />
                            )}
                            <span className={cn(isCurrent && "font-medium")}>{t(`synthesisProgress.${id}`)}</span>
                        </div>
                    )
                })}
            </div>

            {status === "failed" && (
                <div className="flex items-center gap-2 text-destructive">
                    <AlertCircle className="h-4 w-4" />
                    <span className="text-sm">{t("synthesisProgress.failed")}</span>
                </div>
            )}
        </div>
    )
}
