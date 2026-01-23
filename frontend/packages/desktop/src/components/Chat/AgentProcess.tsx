import { Check, ChevronDown, ChevronRight, Loader2, Terminal } from "lucide-react"
import { useState } from "react"
import { useTranslation } from "react-i18next"
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from "@evoloop/shared/components/ui/collapsible"

export interface AgentProcessStep {
    id: string
    tool: string
    input: any
    output: string
    status: "success" | "failure" | "running"
    duration?: number
}

interface AgentProcessProps {
    steps: AgentProcessStep[]
    isStreaming?: boolean
}

export function AgentProcess({ steps, isStreaming }: AgentProcessProps) {
    const { t } = useTranslation()
    const [isOpen, setIsOpen] = useState(false)

    if (!steps || steps.length === 0) return null

    // Determine summarization
    const runningStep = steps.find(s => s.status === "running")
    const completedCount = steps.filter(s => s.status !== "running").length

    return (
        <div className="mb-4 rounded-md border bg-card/40 px-3 py-2 text-sm shadow-sm transition-all hover:bg-card/60">
            <Collapsible open={isOpen} onOpenChange={setIsOpen}>
                <div className="flex items-center justify-between">
                    <div className="flex items-center gap-2">
                        <span className="flex h-5 w-5 items-center justify-center rounded-full bg-primary/10">
                            {isStreaming && runningStep ? (
                                <Loader2 className="h-3 w-3 animate-spin text-primary" />
                            ) : (
                                <Terminal className="h-3 w-3 text-primary" />
                            )}
                        </span>
                        <span className="font-medium text-foreground text-xs">
                            {isStreaming && runningStep
                                ? t('chat.process.executing', { tool: runningStep.tool })
                                : t('chat.process.summary', { count: completedCount })
                            }
                        </span>
                    </div>

                    <CollapsibleTrigger asChild>
                        <button className="flex items-center gap-1 text-[10px] uppercase tracking-wider font-semibold text-muted-foreground hover:text-foreground">
                            {isOpen ? t('chat.process.hide') : t('chat.process.show')}
                            {isOpen ? <ChevronDown size={12} /> : <ChevronRight size={12} />}
                        </button>
                    </CollapsibleTrigger>
                </div>

                <CollapsibleContent className="mt-3 space-y-3 border-t border-border/50 pt-3">
                    {steps.map((step, idx) => (
                        <div key={idx} className="group relative flex gap-3">
                            {/* Timeline Line */}
                            {idx !== steps.length - 1 && (
                                <div className="absolute left-[9px] top-6 bottom-[-12px] w-[1px] bg-border/60" />
                            )}

                            {/* Icon */}
                            <div className="shrink-0 z-10 bg-background rounded-full border border-transparent group-hover:border-border transition-colors">
                                {step.status === "running" ? (
                                    <Loader2 className="h-5 w-5 p-0.5 animate-spin text-primary" />
                                ) : step.status === "failure" ? (
                                    <div className="flex h-5 w-5 items-center justify-center rounded-full bg-red-500/10 text-red-500 text-xs font-bold">!</div>
                                ) : (
                                    <div className="flex h-5 w-5 items-center justify-center rounded-full bg-primary/10">
                                        <Check className="h-3 w-3 text-primary" />
                                    </div>
                                )}
                            </div>

                            {/* Content */}
                            <div className="flex-1 min-w-0">
                                <div className="flex items-center gap-2">
                                    <span className="font-mono text-xs font-semibold text-foreground/90">{step.tool}</span>
                                    {step.duration && <span className="text-[10px] text-muted-foreground">{step.duration}ms</span>}
                                </div>
                                <div className="text-xs text-muted-foreground truncate w-full">
                                    {formatInput(step.input, t)}
                                </div>

                                {/* Output Preview */}
                                {step.output && (
                                    <div className="mt-1.5 rounded-md bg-muted/40 p-2 font-mono text-[10px] text-muted-foreground max-h-[150px] overflow-y-auto whitespace-pre-wrap border border-transparent hover:border-border transition-colors">
                                        {step.output}
                                    </div>
                                )}
                            </div>
                        </div>
                    ))}
                </CollapsibleContent>
            </Collapsible>
        </div>
    )
}

function formatInput(input: any, t: any): string {
    if (typeof input === 'string') return input
    if (!input) return ""

    // Specific Formatters
    if (input.path) return t('chat.process.path', { path: input.path })
    if (input.start_path) return t('chat.process.path', { path: input.start_path })
    if (input.query) return t('chat.process.query', { query: input.query })
    if (input.command) return t('chat.process.command', { command: input.command })

    try {
        const str = JSON.stringify(input)
        return str.length > 50 ? str.slice(0, 50) + "..." : str
    } catch {
        return String(input)
    }
}
