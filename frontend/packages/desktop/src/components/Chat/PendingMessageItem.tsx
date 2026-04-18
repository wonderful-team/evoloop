import { useChatStore } from "@/stores/chatStore"
import { Bot, Brain, ChevronDown, ChevronRight, Loader2, Terminal } from "lucide-react"
import { Avatar, AvatarFallback, AvatarImage } from "@evoloop/shared/components/ui/avatar"
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from "@evoloop/shared/components/ui/collapsible"
import { Button } from "@evoloop/shared/components/ui/button"
import { AgentProcess } from "./AgentProcess"
import { MessageContent } from "./MessageContent"
import { ArtifactsList } from "./Artifacts/ArtifactsList"
import { ThoughtCard } from "./ThoughtCard"
import { HumanRequestCard } from "./HumanRequestCard"
import { QuotaExhaustedCard } from "./QuotaExhaustedCard"
import { memo, useState } from "react"
import { useTranslation } from "react-i18next"

export const PendingMessageItem = memo(() => {
    const { t } = useTranslation()
    const [stepsOpen, setStepsOpen] = useState(false)

    // Connect to granular store selectors for performance
    const streamedContent = useChatStore((s) => s.streamedContent)
    const steps = useChatStore((s) => s.steps)
    const artifacts = useChatStore((s) => s.artifacts)
    const status = useChatStore((s) => s.status)
    const thoughts = useChatStore((s) => s.thoughts) || []
    const humanRequest = useChatStore((s) => s.humanRequest)
    const streamState = useChatStore((s) => s.streamState)

    // Calculate running steps count for summary
    const runningStepsCount = steps.filter(s => s.status === "running").length
    const completedStepsCount = steps.filter(s => s.status === "done").length
    const hasSteps = steps.length > 0

    // Only render if there is active content or running status
    // But typically MessageList controls when to show this.

    return (
        <div className="group relative flex gap-3 items-start mb-6 animate-in fade-in slide-in-from-bottom-2 chat-timeline-container">
            {/* Thread Line */}
            <div className="chat-timeline-line" />

            {/* Avatar */}
            <div className="shrink-0 w-8 flex flex-col items-center relative z-10">
                <Avatar className="h-8 w-8 mt-1 border-none bg-muted shadow-none">
                    <AvatarImage src="/bot-avatar.png" />
                    <AvatarFallback>
                        <Bot size={16} className="animate-pulse text-primary" />
                    </AvatarFallback>
                </Avatar>
            </div>

            <div className={`relative flex-1 w-0 max-w-[90%] sm:max-w-[85%] min-w-0 flex flex-col gap-1`}>
                
                {/* 1. Action Stream (Thinking + Steps) - ALWAYS ABOVE during pending */}
                <div className="chat-action-stream empty:hidden">
                    {/* Thoughts (Reasoning) */}
                    {thoughts.length > 0 && (
                        <Collapsible defaultOpen={true} className="w-full">
                            <CollapsibleTrigger asChild>
                                <Button
                                    variant="ghost"
                                    size="sm"
                                    className="h-7 px-2 text-[11px] text-muted-foreground hover:text-foreground hover:bg-muted/50 flex items-center gap-2 w-full justify-start rounded-md"
                                >
                                    <Brain className="h-3.5 w-3.5 text-primary/70" />
                                    <span className="font-semibold uppercase tracking-wider opacity-70">
                                        {t("chat.steps.thoughts")} ({thoughts.length})
                                    </span>
                                    <ChevronRight className="h-3.5 w-3.5 ml-auto opacity-40 group-data-[state=open]:rotate-90 transition-transform" />
                                </Button>
                            </CollapsibleTrigger>
                            <CollapsibleContent className="mt-1 space-y-1">
                                {thoughts.map(thought => (
                                    <ThoughtCard key={thought.id} thought={thought} />
                                ))}
                            </CollapsibleContent>
                        </Collapsible>
                    )}

                    {/* Task Execution Steps */}
                    {hasSteps && (
                        <Collapsible
                            open={stepsOpen}
                            onOpenChange={setStepsOpen}
                            className="w-full"
                        >
                            <AgentProcess 
                                steps={steps} 
                                isStreaming={steps.some((s) => s.status === "running")}
                                header={
                                    <CollapsibleTrigger asChild>
                                        <Button
                                            variant="ghost"
                                            size="sm"
                                            className="h-8 px-3 text-[11px] text-muted-foreground hover:text-foreground hover:bg-transparent flex items-center gap-2 w-full justify-start rounded-none"
                                        >
                                            <Terminal className="h-3.5 w-3.5 opacity-70" />
                                            <span className="font-medium">
                                                {runningStepsCount > 0
                                                    ? t("chat.steps.executing") + ` ${runningStepsCount} ${t("chat.steps.tools")}...`
                                                    : completedStepsCount === steps.length
                                                        ? t("chat.steps.completed") + ` ${steps.length} ${t("chat.steps.tools")}`
                                                        : t("chat.steps.progress") + ` ${completedStepsCount}/${steps.length}`
                                                }
                                            </span>
                                            <ChevronDown className={`h-3.5 w-3.5 ml-auto transition-transform ${stepsOpen ? "" : "-rotate-90"}`} />
                                        </Button>
                                    </CollapsibleTrigger>
                                }
                            />
                        </Collapsible>
                    )}
                </div>

                {/* 2. Main Response Bubble */}
                {(streamedContent || status === "running") && (
                    <div className="rounded-xl px-4 py-3 text-sm leading-relaxed bg-muted/50 text-foreground border border-border/40 min-h-[40px] w-fit max-w-full">
                        {streamedContent ? (
                            <>
                                <MessageContent content={streamedContent} />
                                {status === "running" && (
                                    <span className="inline-block w-1.5 h-4 ml-1 align-middle bg-primary animate-pulse" />
                                )}
                            </>
                        ) : (
                             <div className="flex flex-col gap-1 w-full min-w-[200px]">
                                <div className="flex items-center gap-2 text-xs text-muted-foreground italic">
                                    <Loader2 className="h-3 w-3 animate-spin" />
                                    {streamState.currentThinking || t("chat.interface.agentThinking")}
                                </div>
                                {streamState.overallProgress > 0 && streamState.overallProgress < 100 && (
                                    <div className="w-full h-1 bg-muted-foreground/10 rounded-full overflow-hidden mt-1">
                                        <div 
                                            className="h-full bg-primary/40 transition-all duration-300"
                                            style={{ width: `${streamState.overallProgress}%` }}
                                        />
                                    </div>
                                )}
                            </div>
                        )}
                    </div>
                )}

                {/* 3. Artifacts */}
                {artifacts.length > 0 && (
                    <div className="w-full">
                        <ArtifactsList artifacts={artifacts} />
                    </div>
                )}

                {/* 4. HITL Request (Interruption) */}
                {status === "interrupted" && humanRequest && (
                    <div className="mt-2 w-full">
                        <HumanRequestCard request={humanRequest} />
                    </div>
                )}

                {/* 5. Quota Exhausted Card */}
                {status === "quota_exhausted" && (
                    <div className="mt-2 w-full">
                        <QuotaExhaustedCard />
                    </div>
                )}
            </div>
        </div>
    )
})

PendingMessageItem.displayName = "PendingMessageItem"
