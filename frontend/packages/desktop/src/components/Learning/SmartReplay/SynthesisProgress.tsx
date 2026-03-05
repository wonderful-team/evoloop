/**
 * SynthesisProgress - Display synthesis progress with animated indicators
 */

import { Loader2, CheckCircle2, Circle, AlertCircle } from "lucide-react"
import { cn } from "@evoloop/shared/lib/utils"

interface SynthesisProgressProps {
    status: string
    progress: number
    phase: string
}

const phases = [
    { id: "loading_data", label: "Loading data..." },
    { id: "extracting_keyframes", label: "Extracting keyframes..." },
    { id: "analyzing_frames", label: "Analyzing frames with AI..." },
    { id: "understanding_phases", label: "Understanding task flow..." },
    { id: "identifying_steps", label: "Identifying critical steps..." },
    { id: "generating_macro", label: "Generating macro script..." },
    { id: "generating_metadata", label: "Generating skill documentation..." },
    { id: "completed", label: "Completed!" },
]

export function SynthesisProgress({ status, progress, phase }: SynthesisProgressProps) {
    const currentPhaseIndex = phases.findIndex((p) => phase.includes(p.id) || p.id === phase)

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
                {phases.map((p, idx) => {
                    const isCompleted = idx < currentPhaseIndex
                    const isCurrent = idx === currentPhaseIndex
                    const isPending = idx > currentPhaseIndex

                    return (
                        <div
                            key={p.id}
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
                            <span className={cn(isCurrent && "font-medium")}>{p.label}</span>
                        </div>
                    )
                })}
            </div>

            {status === "failed" && (
                <div className="flex items-center gap-2 text-destructive">
                    <AlertCircle className="h-4 w-4" />
                    <span className="text-sm">Synthesis failed. Please try again.</span>
                </div>
            )}
        </div>
    )
}
