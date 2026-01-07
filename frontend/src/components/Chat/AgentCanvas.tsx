import { Bot, ChevronDown, ChevronRight, Loader2, X } from "lucide-react"
import { memo, useState } from "react"
import { useTranslation } from "react-i18next"
import { useChatStore } from "@/stores/chatStore"
import { Avatar, AvatarFallback, AvatarImage } from "../ui/avatar"
import { Button } from "../ui/button"
import { cn } from "@/lib/utils"
import { ArtifactsList } from "./Artifacts/ArtifactsList"
import { HumanRequestCard } from "./HumanRequestCard"
import { MessageContent } from "./MessageContent"
import { TaskSteps } from "./TaskSteps"
import { ThoughtCard } from "./ThoughtCard"

/**
 * TaskSummaryBar - Single line task status summary
 * Format: ✨ {MODE} | {task_name} ({done}/{total})
 */
const TaskSummaryBar = memo(({
    tasks,
    agentState,
    isExpanded,
    onToggle
}: {
    tasks: any[]
    agentState: any
    isExpanded: boolean
    onToggle: () => void
}) => {
    const doneCount = tasks.filter(t => t.status === "done").length
    const totalCount = tasks.length
    const displayMode = agentState?.mode || "BUSY"
    const displayTask = agentState?.task_name || "Working..."

    const getModeColor = (mode: string) => {
        switch (mode.toUpperCase()) {
            case 'PLANNING': return 'text-purple-600 bg-purple-100/50 dark:bg-purple-900/20'
            case 'RESEARCHING':
            case 'DEEP RESEARCH': return 'text-blue-600 bg-blue-100/50 dark:bg-blue-900/20'
            case 'CODING': return 'text-amber-600 bg-amber-100/50 dark:bg-amber-900/20'
            case 'REVIEWING': return 'text-pink-600 bg-pink-100/50 dark:bg-pink-900/20'
            case 'EXECUTION': return 'text-green-600 bg-green-100/50 dark:bg-green-900/20'
            default: return 'text-muted-foreground bg-muted'
        }
    }

    if (totalCount === 0) return null

    return (
        <button
            type="button"
            onClick={onToggle}
            className="w-full flex items-center gap-2 px-3 py-2 bg-muted/30 hover:bg-muted/50 rounded-lg transition-colors text-left"
        >
            <Loader2 size={14} className="animate-spin text-primary shrink-0" />
            <span className={`text-[10px] font-bold px-1.5 py-0.5 rounded uppercase tracking-wider shrink-0 ${getModeColor(displayMode)}`}>
                {displayMode}
            </span>
            <span className="text-sm text-muted-foreground truncate flex-1">
                {displayTask}
            </span>
            <span className="text-xs text-muted-foreground shrink-0">
                ({doneCount}/{totalCount})
            </span>
            {isExpanded ? (
                <ChevronDown size={14} className="text-muted-foreground shrink-0" />
            ) : (
                <ChevronRight size={14} className="text-muted-foreground shrink-0" />
            )}
        </button>
    )
})
TaskSummaryBar.displayName = "TaskSummaryBar"

/**
 * AgentCanvas - Right-side sliding panel for active Agent state
 * Shows streaming content, tasks, artifacts, and HITL requests
 */
export const AgentCanvas = memo(({
    isOpen,
    onClose
}: {
    isOpen: boolean
    onClose: () => void
}) => {
    const { t } = useTranslation()
    const [isTasksExpanded, setIsTasksExpanded] = useState(false)



    // ... imports

    // Granular Store Selectors
    const streamedContent = useChatStore((s) => s.streamedContent)
    const tasks = useChatStore((s) => s.tasks)
    const artifacts = useChatStore((s) => s.artifacts)
    const status = useChatStore((s) => s.status)
    const agentState = useChatStore((s) => s.agentState)
    const thoughts = useChatStore((s) => s.thoughts) || [] // Phase 6: Thoughts
    const humanRequest = useChatStore((s) => s.humanRequest)

    // ...

    return (
        <div
            className={cn(
                "fixed top-0 right-0 h-full bg-background border-l shadow-2xl z-50 transition-transform duration-300 ease-in-out flex flex-col",
                "w-[400px] max-w-[90vw]",
                isOpen ? "translate-x-0" : "translate-x-full"
            )}
        >
            {/* Header */}
            <div className="flex items-center justify-between p-3 border-b shrink-0">
                <div className="flex items-center gap-2">
                    <Avatar className="h-6 w-6">
                        <AvatarImage src="/bot-avatar.png" />
                        <AvatarFallback>
                            <Bot size={14} />
                        </AvatarFallback>
                    </Avatar>
                    <span className="font-semibold text-sm">
                        {t("chat.canvas.title", "Agent Working")}
                    </span>
                    {status === "running" && (
                        <Loader2 size={14} className="animate-spin text-primary" />
                    )}
                </div>
                <Button variant="ghost" size="icon" className="h-7 w-7" onClick={onClose}>
                    <X size={16} />
                </Button>
            </div>

            {/* Content */}
            <div className="flex-1 overflow-y-auto p-4 space-y-4">
                {/* HITL Request Card (Priority) */}
                {humanRequest && status === "interrupted" && (
                    <HumanRequestCard request={humanRequest} />
                )}

                {/* Phase 6: Active Thoughts Stream */}
                {thoughts.length > 0 && (
                    <div className="space-y-1">
                        <h4 className="text-xs font-medium text-muted-foreground uppercase tracking-wider mb-2">
                            {t("chat.canvas.thoughts", "Activity Stream")}
                        </h4>
                        {/* Show last 3 thoughts */}
                        {thoughts.slice(-3).reverse().map(thought => (
                            <ThoughtCard key={thought.id} thought={thought} />
                        ))}
                    </div>
                )}

                {/* Task Summary Bar */}
                {tasks.length > 0 && (
                    <div className="space-y-2">
                        <TaskSummaryBar
                            tasks={tasks}
                            agentState={agentState}
                            isExpanded={isTasksExpanded}
                            onToggle={() => setIsTasksExpanded(!isTasksExpanded)}
                        />
                        {isTasksExpanded && (
                            <div className="pl-2 animate-in fade-in slide-in-from-top-2">
                                <TaskSteps tasks={tasks} />
                            </div>
                        )}
                    </div>
                )}

                {/* Artifacts List */}
                {artifacts.length > 0 && (
                    <div className="space-y-2">
                        <h4 className="text-xs font-medium text-muted-foreground uppercase tracking-wider">
                            {t("chat.canvas.artifacts", "Artifacts")}
                        </h4>
                        <ArtifactsList artifacts={artifacts} />
                    </div>
                )}

                {/* Streaming Content */}
                {streamedContent && (
                    <div className="space-y-2">
                        <h4 className="text-xs font-medium text-muted-foreground uppercase tracking-wider">
                            {t("chat.canvas.response", "Response")}
                        </h4>
                        <div className="rounded-lg px-4 py-3 bg-muted text-foreground text-sm leading-relaxed shadow-sm overflow-hidden">
                            <MessageContent content={streamedContent} />
                        </div>
                    </div>
                )}

                {/* Blinking Cursor (when running but no content yet) */}
                {!streamedContent && status === "running" && !humanRequest && (
                    <div className="rounded-lg px-4 py-3 bg-muted text-foreground text-sm leading-relaxed shadow-sm">
                        <span className="inline-block w-1.5 h-4 bg-primary align-middle animate-pulse" />
                    </div>
                )}
            </div>

            {/* Footer Status */}
            <div className="p-3 border-t bg-muted/20 shrink-0">
                <div className="text-xs text-muted-foreground text-center">
                    {status === "running" && t("chat.canvas.statusRunning", "Agent is working...")}
                    {status === "interrupted" && t("chat.canvas.statusWaiting", "Waiting for your input")}
                    {status === "SUMMARIZING" && t("chat.canvas.statusSummarizing", "Summarizing...")}
                </div>
            </div>
        </div >
    )
})

AgentCanvas.displayName = "AgentCanvas"
