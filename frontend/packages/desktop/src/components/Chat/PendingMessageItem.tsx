import { useChatStore } from "@/stores/chatStore"
import { Bot, Loader2 } from "lucide-react"
import { Avatar, AvatarFallback, AvatarImage } from "@evoloop/shared/components/ui/avatar"
import { ExecutionSteps } from "./ExecutionSteps"
import { MessageContent } from "./MessageContent"
import { ArtifactsList } from "./Artifacts/ArtifactsList"
import { ThoughtCard } from "./ThoughtCard"
import { HumanRequestCard } from "./HumanRequestCard"
import { memo } from "react"
import { useTranslation } from "react-i18next"

export const PendingMessageItem = memo(() => {
    const { t } = useTranslation()

    // Connect to granular store selectors for performance
    const streamedContent = useChatStore((s) => s.streamedContent)
    const steps = useChatStore((s) => s.steps)
    const artifacts = useChatStore((s) => s.artifacts)
    const status = useChatStore((s) => s.status)
    const thoughts = useChatStore((s) => s.thoughts) || []
    const humanRequest = useChatStore((s) => s.humanRequest)

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

            <div className="relative max-w-[85%] w-full min-w-0 space-y-2">

                {/* 1. Thoughts (Reasoning) */}
                {thoughts.length > 0 && (
                    <div className="space-y-1 mb-2">
                        {thoughts.map(thought => (
                            <ThoughtCard key={thought.id} thought={thought} />
                        ))}
                    </div>
                )}

                {/* 2. Task Execution Steps */}
                {steps.length > 0 && (
                    <div className="mb-2 w-full">
                        <ExecutionSteps steps={steps as any} />
                    </div>
                )}

                {/* 3. Artifacts (Generated Files/Reports) */}
                {artifacts.length > 0 && (
                    <div className="mb-2 w-full">
                        <ArtifactsList artifacts={artifacts} />
                    </div>
                )}

                {/* 4. Streamed Content (The Response) */}
                {streamedContent && (
                    <div className="rounded-lg px-4 py-3 text-sm leading-relaxed bg-muted text-foreground min-h-[40px]">
                        <MessageContent content={streamedContent} />
                        <span className="inline-block w-1.5 h-4 ml-1 align-middle bg-primary animate-pulse" />
                    </div>
                )}

                {/* 5. HITL Request (Interruption) */}
                {status === "interrupted" && humanRequest && (
                    <div className="mt-2 w-full">
                        <HumanRequestCard request={humanRequest} />
                    </div>
                )}

                {/* 6. Loading Indicator (if nothing else is showing yet) */}
                {!streamedContent && steps.length === 0 && thoughts.length === 0 && status === "running" && (
                    <div className="flex items-center gap-2 text-xs text-muted-foreground italic h-10">
                        <Loader2 className="h-3 w-3 animate-spin" />
                        {t("chat.interface.agentThinking", "Thinking...")}
                    </div>
                )}
            </div>
        </div>
    )
})

PendingMessageItem.displayName = "PendingMessageItem"
