import { useMemo } from "react"
import { useTranslation } from "react-i18next"
import { Loader2 } from "lucide-react"
import { motion, AnimatePresence } from "framer-motion"
import { SmartChatMessageItem, type Message } from "./ChatMessageItem"
import { ChatWelcome } from "./ChatWelcome"
import { ToolExecutionGroup } from "./ToolExecutionGroup"

interface MessageListProps {
    messages: Message[]
    hasMoreHistory?: boolean
    isLoadingHistory?: boolean
    onAddToMemory?: (text: string) => void
    onRewind?: (msg: Message) => void
    onRetry?: (msg: Message) => void
    onQuote?: (msg: Message) => void
    onViewChangeset?: () => void
}

type RenderItem = 
    | { type: "message"; data: Message & { showDate?: boolean } }
    | { type: "tool_group"; data: { steps: Message[]; showDate?: boolean; id: string } }

/** Merge multiple AI messages from the same turn into a single message. */
function mergeAiMessages(msgs: Message[]): Message | null {
    if (msgs.length === 0) return null
    const first = msgs[0]
    const last = msgs[msgs.length - 1]

    const paragraphs = msgs
        .map((m) => m.content?.trim())
        .filter(Boolean)

    return {
        ...first,
        content: paragraphs.join("\n\n"),
        thinking: msgs.map((m) => m.thinking).filter(Boolean).join("\n\n") || undefined,
        status: msgs.some((m) => m.status === "streaming") ? "streaming" : (last.status || "completed"),
        changeset_count: msgs.reduce((sum, m) => sum + (m.changeset_count || 0), 0),
        has_file_operations: msgs.some((m) => m.has_file_operations),
        timestamp: last.timestamp || first.timestamp,
        humanRequest: msgs.find((m) => m.humanRequest)?.humanRequest,
    }
}

export function MessageList({
    messages,
    hasMoreHistory = false,
    isLoadingHistory = false,
    onAddToMemory,
    onRewind,
    onRetry,
    onQuote,
    onViewChangeset,
}: MessageListProps) {
    const { t } = useTranslation()

    const renderItems = useMemo(() => {
        const items: RenderItem[] = []
        let prevTimestamp: string | undefined
        let currentAiGroup: Message[] = []
        let currentToolGroup: Message[] = []

        const flushAiGroup = () => {
            if (currentAiGroup.length > 0) {
                const merged = mergeAiMessages(currentAiGroup)
                if (merged) {
                    const showDate = !!merged.timestamp &&
                        (!prevTimestamp || new Date(merged.timestamp).toDateString() !== new Date(prevTimestamp).toDateString())
                    items.push({ type: "message", data: { ...merged, showDate } })
                    prevTimestamp = merged.timestamp
                }
                currentAiGroup = []
            }
        }

        const flushToolGroup = () => {
            if (currentToolGroup.length > 0) {
                const first = currentToolGroup[0]
                const showDate = !!first.timestamp &&
                    (!prevTimestamp || new Date(first.timestamp).toDateString() !== new Date(prevTimestamp).toDateString())
                
                items.push({ 
                    type: "tool_group", 
                    data: { 
                        steps: [...currentToolGroup], 
                        showDate,
                        id: `group-${first.id}`
                    } 
                })
                prevTimestamp = first.timestamp
                currentToolGroup = []
            }
        }

        for (const msg of messages) {
            if (msg.role === "human") {
                flushAiGroup()
                flushToolGroup()
                const showDate = !!msg.timestamp &&
                    (!prevTimestamp || new Date(msg.timestamp).toDateString() !== new Date(prevTimestamp).toDateString())
                items.push({ type: "message", data: { ...msg, showDate } })
                prevTimestamp = msg.timestamp
            } else if (msg.role === "ai") {
                flushToolGroup()
                currentAiGroup.push(msg)
            } else if (msg.role === "tool") {
                flushAiGroup()
                currentToolGroup.push(msg)
            }
        }

        flushAiGroup()
        flushToolGroup()
        return items
    }, [messages])

    return (
        <div className="min-h-0 min-w-0 relative">
            <div className="space-y-6 px-4 sm:px-6 lg:px-8 pb-4 min-w-0">
                {isLoadingHistory && (
                    <motion.div 
                        initial={{ opacity: 0 }}
                        animate={{ opacity: 1 }}
                        className="py-4 text-center text-muted-foreground"
                    >
                        <Loader2 className="w-5 h-5 animate-spin mx-auto mb-2" />
                        <span className="text-xs">{t("chat.loadingHistory")}</span>
                    </motion.div>
                )}

                {hasMoreHistory && !isLoadingHistory && messages.length > 0 && (
                    <div className="py-3 text-center text-muted-foreground/50 text-xs">
                        {t("chat.scrollToLoadMore")}
                    </div>
                )}

                {messages.length === 0 && !isLoadingHistory && (
                    <ChatWelcome />
                )}

                <AnimatePresence initial={false} mode="popLayout">
                    {renderItems.map((item, index) => {
                        if (item.type === "message") {
                            return (
                                <motion.div 
                                    key={`${item.data.id}-${index}`}
                                    initial={{ opacity: 0, y: 10 }}
                                    animate={{ opacity: 1, y: 0 }}
                                    transition={{ type: "spring", stiffness: 400, damping: 30 }}
                                    layout="position"
                                >
                                    <SmartChatMessageItem
                                        msg={item.data}
                                        isGrouped={false}
                                        showAvatar={true}
                                        onAddToMemory={onAddToMemory ? (txt) => onAddToMemory(txt) : undefined}
                                        onRewind={onRewind ? () => onRewind(item.data) : undefined}
                                        onRetry={onRetry ? () => onRetry(item.data) : undefined}
                                        onQuote={() => onQuote?.(item.data)}
                                        onViewChangeset={onViewChangeset}
                                    />
                                </motion.div>
                            )
                        } else {
                            return (
                                <motion.div 
                                    key={`${item.data.id}-${index}`}
                                    initial={{ opacity: 0, scale: 0.98 }}
                                    animate={{ opacity: 1, scale: 1 }}
                                    layout="position"
                                >
                                    <ToolExecutionGroup 
                                        steps={item.data.steps} 
                                    />
                                </motion.div>
                            )
                        }
                    })}
                </AnimatePresence>
            </div>
        </div>
    )
}
