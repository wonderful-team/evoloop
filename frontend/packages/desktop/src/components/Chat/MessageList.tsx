import { useRef, useEffect, useMemo } from "react"
import { useTranslation } from "react-i18next"
import { Bot, HelpCircle, FileText, ListTodo, Search } from "lucide-react"
import { Button } from "@evoloop/shared/components/ui/button"
import { ChatMessageItem, type Message } from "./ChatMessageItem"
import { PendingMessageItem } from "./PendingMessageItem"

interface MessageListProps {
    messages: Message[]
    isAgentWorking: boolean
    onAddToMemory?: (text: string) => void
    onRewind?: (msg: Message) => void
    onRetry?: (msg: Message) => void
    onQuote?: (msg: Message) => void
    onStarterClick?: (text: string) => void
}

export function MessageList({
    messages,
    isAgentWorking,
    onAddToMemory,
    onRewind,
    onRetry,
    onQuote,
    onStarterClick
}: MessageListProps) {
    const { t } = useTranslation()
    const scrollRef = useRef<HTMLDivElement>(null)

    // Grouping Logic
    const groupedMessages = useMemo(() => {
        const groups: (Message & { showDate?: boolean; isGrouped?: boolean; showAvatar?: boolean })[] = []

        messages.forEach((msg, index) => {
            const prevMsg = messages[index - 1]

            // Date Separator Logic
            let showDate = false
            if (msg.timestamp) {
                const date = new Date(msg.timestamp).toDateString()
                const prevDate = prevMsg?.timestamp ? new Date(prevMsg.timestamp).toDateString() : null
                if (date !== prevDate) {
                    showDate = true
                }
            }

            // Grouping Logic (Same Role, < 5 mins diff)
            const isGrouped = prevMsg &&
                prevMsg.role === msg.role &&
                !showDate &&
                // check time diff 
                (msg.timestamp && prevMsg.timestamp ? (new Date(msg.timestamp).getTime() - new Date(prevMsg.timestamp).getTime() < 5 * 60 * 1000) : true)

            // First message of a group gets the avatar
            const showAvatar = !isGrouped

            groups.push({
                ...msg,
                showDate,
                isGrouped,
                showAvatar
            })
        })
        return groups
    }, [messages])

    // Auto-scroll (simplified)
    useEffect(() => {
        scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: "smooth" })
    }, [messages.length, isAgentWorking]) // Scroll on new messages

    return (
        <div className="flex-1 overflow-y-auto min-h-0 scroll-smooth" ref={scrollRef}>
            <div className="space-y-2 max-w-4xl mx-auto pb-4">

                {/* Empty State */}
                {messages.length === 0 && (
                    <div className="flex flex-col items-center justify-center h-full text-muted-foreground mt-10 animate-in fade-in slide-in-from-bottom-4">
                        <Bot size={48} className="mb-4 opacity-20" />
                        <p className="text-lg font-medium mb-1">{t("chat.interface.welcome", "How can I help you today?")}</p>
                        <p className="text-sm opacity-60 mb-8">{t("chat.interface.startPrompt", "Start a new conversation or choose a task below.")}</p>

                        <div className="grid grid-cols-2 gap-3 w-full max-w-md">
                            <Button variant="outline" className="h-auto py-3 justify-start gap-3 bg-muted/30 hover:bg-muted/60" onClick={() => onStarterClick?.(t("chat.context.starter.analyze", "Analyze current codebase structure"))}>
                                <div className="p-2 bg-blue-500/10 rounded-full shrink-0"><Search size={16} className="text-blue-500" /></div>
                                <div className="flex flex-col items-start"><span className="text-sm font-medium">{t("chat.context.starter.analyzeLabel", "Analyze Codebase")}</span><span className="text-[10px] text-muted-foreground opacity-70">{t("chat.context.starter.analyzeDesc", "Explore architecture & files")}</span></div>
                            </Button>
                            <Button variant="outline" className="h-auto py-3 justify-start gap-3 bg-muted/30 hover:bg-muted/60" onClick={() => onStarterClick?.(t("chat.context.starter.plan", "Create a new implementation plan"))}>
                                <div className="p-2 bg-purple-500/10 rounded-full shrink-0"><FileText size={16} className="text-purple-500" /></div>
                                <div className="flex flex-col items-start"><span className="text-sm font-medium">{t("chat.context.starter.planLabel", "Create Plan")}</span><span className="text-[10px] text-muted-foreground opacity-70">{t("chat.context.starter.planDesc", "Draft a roadmap for changes")}</span></div>
                            </Button>
                            <Button variant="outline" className="h-auto py-3 justify-start gap-3 bg-muted/30 hover:bg-muted/60" onClick={() => onStarterClick?.(t("chat.context.starter.tasks", "What tasks are currently pending?"))}>
                                <div className="p-2 bg-green-500/10 rounded-full shrink-0"><ListTodo size={16} className="text-green-500" /></div>
                                <div className="flex flex-col items-start"><span className="text-sm font-medium">{t("chat.context.starter.tasksLabel", "Check Tasks")}</span><span className="text-[10px] text-muted-foreground opacity-70">{t("chat.context.starter.tasksDesc", "Review active todo items")}</span></div>
                            </Button>
                            <Button variant="outline" className="h-auto py-3 justify-start gap-3 bg-muted/30 hover:bg-muted/60" onClick={() => onStarterClick?.(t("chat.context.starter.help", "Help me understand this project"))}>
                                <div className="p-2 bg-amber-500/10 rounded-full shrink-0"><HelpCircle size={16} className="text-amber-500" /></div>
                                <div className="flex flex-col items-start"><span className="text-sm font-medium">{t("chat.context.starter.helpLabel", "Project Help")}</span><span className="text-[10px] text-muted-foreground opacity-70">{t("chat.context.starter.helpDesc", "Get guidance on the system")}</span></div>
                            </Button>
                        </div>
                    </div>
                )}

                {/* Message List */}
                {groupedMessages.map((msg, index) => (
                    <div key={msg.id || index}>
                        {/* Date Separator */}
                        {msg.showDate && msg.timestamp && (
                            <div className="flex items-center gap-4 my-6">
                                <div className="h-px bg-border flex-1" />
                                <span className="text-[10px] font-medium text-muted-foreground uppercase tracking-wider">
                                    {new Date(msg.timestamp).toLocaleDateString(undefined, { weekday: 'short', month: 'short', day: 'numeric' })}
                                </span>
                                <div className="h-px bg-border flex-1" />
                            </div>
                        )}

                        <ChatMessageItem
                            msg={msg}
                            isGrouped={msg.isGrouped}
                            showAvatar={msg.showAvatar}
                            onAddToMemory={onAddToMemory ? (txt) => onAddToMemory(txt) : undefined}
                            onRewind={onRewind ? () => onRewind(msg) : undefined}
                            onRetry={onRetry ? () => onRetry(msg) : undefined}
                            onQuote={() => onQuote?.(msg)}
                        />
                    </div>
                ))}

                {/* Agent Working (Pending Message) */}
                {isAgentWorking && (
                    <PendingMessageItem />
                )}
            </div>
        </div>
    )
}
