import { useChatStore } from "@/stores/chatStore"
import { Bot, Brain, ChevronDown, ChevronRight, Loader2, Terminal } from "lucide-react"
import { Avatar, AvatarFallback, AvatarImage } from "@evoloop/shared/components/ui/avatar"
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from "@evoloop/shared/components/ui/collapsible"
import { Button } from "@evoloop/shared/components/ui/button"
import { ExecutionSteps } from "./ExecutionSteps"
import { MessageContent } from "./MessageContent"
import { ArtifactsList } from "./Artifacts/ArtifactsList"
import { ThoughtCard } from "./ThoughtCard"
import { HumanRequestCard } from "./HumanRequestCard"
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
        <div className="group relative flex gap-3 items-start mb-6 animate-in fade-in slide-in-from-bottom-2">
            {/* Avatar */}
            <div className="shrink-0 w-8 flex flex-col items-center">
                <Avatar className="h-8 w-8 mt-1 border border-primary/20">
                    <AvatarImage src="/bot-avatar.png" />
                    <AvatarFallback>
                        <Bot size={16} className="animate-pulse text-primary" />
                    </AvatarFallback>
                </Avatar>
            </div>

            <div className="relative max-w-full w-full min-w-0 space-y-2">

                {/* 1. Streamed Content (The Response) - AI FIRST */}
                {(streamedContent || status === "running") && (
                    <div className="rounded-lg px-4 py-3 text-sm leading-relaxed bg-muted text-foreground min-h-[40px]">
                        {streamedContent ? (
                            <>
                                <MessageContent content={streamedContent} />
                                {status === "running" && (
                                    <span className="inline-block w-1.5 h-4 ml-1 align-middle bg-primary animate-pulse" />
                                )}
                            </>
                        ) : (
                             <div className="flex flex-col gap-1 w-full">
                                <div className="flex items-center gap-2 text-xs text-muted-foreground italic">
                                    <Loader2 className="h-3 w-3 animate-spin" />
                                    {streamState.currentThinking || t("chat.interface.agentThinking", "Thinking...")}
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

                {/* 2. Thoughts (Reasoning) - Collapsible, Secondary, Default Collapsed */}
                {thoughts.length > 0 && (
                    <Collapsible defaultOpen={false} className="w-full">
                        <CollapsibleTrigger asChild>
                            <Button
                                variant="ghost"
                                size="sm"
                                className="h-7 px-2 text-xs text-muted-foreground hover:text-foreground hover:bg-muted/50 flex items-center gap-2 w-full justify-start"
                            >
                                <Brain className="h-3.5 w-3.5" />
                                <span className="font-medium">
                                    {thoughts.length} {t("chat.steps.thoughts", "thoughts")}
                                </span>
                                <ChevronRight className="h-3.5 w-3.5 ml-auto" />
                            </Button>
                        </CollapsibleTrigger>
                        <CollapsibleContent className="mt-1 space-y-1">
                            {thoughts.map(thought => (
                                <ThoughtCard key={thought.id} thought={thought} />
                            ))}
                        </CollapsibleContent>
                    </Collapsible>
                )}

                {/* 3. Task Execution Steps - Collapsed by default with compact summary */}
                {hasSteps && (
                    <Collapsible
                        open={stepsOpen}
                        onOpenChange={setStepsOpen}
                        className="w-full"
                    >
                        {/* Compact Summary Bar */}
                        <CollapsibleTrigger asChild>
                            <Button
                                variant="ghost"
                                size="sm"
                                className="h-7 px-2 text-xs text-muted-foreground hover:text-foreground hover:bg-muted/50 flex items-center gap-2 w-full justify-start"
                            >
                                <Terminal className="h-3.5 w-3.5" />
                                <span className="font-medium">
                                    {runningStepsCount > 0
                                        ? t("chat.steps.executing", "Executing") + ` ${runningStepsCount} ${t("chat.steps.tools", "tools")}...`
                                        : completedStepsCount === steps.length
                                            ? t("chat.steps.completed", "Completed") + ` ${steps.length} ${t("chat.steps.tools", "tools")}`
                                            : t("chat.steps.progress", "Progress") + ` ${completedStepsCount}/${steps.length}`
                                    }
                                </span>
                                {stepsOpen ? (
                                    <ChevronDown className="h-3.5 w-3.5 ml-auto" />
                                ) : (
                                    <ChevronRight className="h-3.5 w-3.5 ml-auto" />
                                )}
                            </Button>
                        </CollapsibleTrigger>
                        <CollapsibleContent className="mt-1">
                            <ExecutionSteps steps={steps as any} />
                        </CollapsibleContent>
                    </Collapsible>
                )}

                {/* 4. Artifacts (Generated Files/Reports) */}
                {artifacts.length > 0 && (
                    <div className="w-full">
                        <ArtifactsList artifacts={artifacts} />
                    </div>
                )}

                {/* 5. HITL Request (Interruption) */}
                {status === "interrupted" && humanRequest && (
                    <div className="mt-2 w-full">
                        <HumanRequestCard request={humanRequest} />
                    </div>
                )}
            </div>
        </div>
    )
})

PendingMessageItem.displayName = "PendingMessageItem"
