import { useMemo } from "react"
import { useTranslation } from "react-i18next"
import { Loader2 } from "lucide-react"
import { SmartChatMessageItem, type Message } from "./ChatMessageItem"
import { ChatWelcome } from "./ChatWelcome"

interface MessageListProps {
    messages: Message[]
    hasMoreHistory?: boolean
    isLoadingHistory?: boolean
    onAddToMemory?: (text: string) => void
    onRewind?: (msg: Message) => void
    onRetry?: (msg: Message) => void
    onQuote?: (msg: Message) => void
    onViewChangeset?: () => void // Callback when user clicks to view changeset
}

interface Turn {
    human?: Message
    ai: Message[]
}

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

    // Group messages by conversation turn.
    // A turn = one human message + all consecutive AI/Tool messages that follow it.
    const renderItems = useMemo(() => {
        const items: (Message & { showDate?: boolean })[] = []
        let prevTimestamp: string | undefined
        let currentAiGroup: Message[] = []

        const flushAiGroup = () => {
            if (currentAiGroup.length > 0) {
                const merged = mergeAiMessages(currentAiGroup)
                if (merged) {
                    const showDate = !!merged.timestamp &&
                        (!prevTimestamp || new Date(merged.timestamp).toDateString() !== new Date(prevTimestamp).toDateString())
                    items.push({ ...merged, showDate })
                    prevTimestamp = merged.timestamp
                }
                currentAiGroup = []
            }
        }

        for (const msg of messages) {
            if (msg.role === "human") {
                flushAiGroup()
                const showDate = !!msg.timestamp &&
                    (!prevTimestamp || new Date(msg.timestamp).toDateString() !== new Date(prevTimestamp).toDateString())
                items.push({ ...msg, showDate })
                prevTimestamp = msg.timestamp
            } else if (msg.role === "ai") {
                currentAiGroup.push(msg)
            } else if (msg.role === "tool") {
                // When we hit a tool message, we flush any AI thinking/content before it,
                // then render the tool message, then continue.
                flushAiGroup()
                const showDate = !!msg.timestamp &&
                    (!prevTimestamp || new Date(msg.timestamp).toDateString() !== new Date(prevTimestamp).toDateString())
                items.push({ ...msg, showDate })
                prevTimestamp = msg.timestamp
            }
        }

        flushAiGroup()
        return items
    }, [messages])

    return (
        <div className="min-h-0 min-w-0 relative">
            <div className="space-y-6 px-4 sm:px-6 lg:px-8 pb-4 min-w-0">
                {/* Loading Indicator at Top */}
                {isLoadingHistory && (
                    <div className="py-4 text-center text-muted-foreground">
                        <Loader2 className="w-5 h-5 animate-spin mx-auto mb-2" />
                        <span className="text-xs">{t("chat.loadingHistory")}</span>
                    </div>
                )}

                {/* Load More Hint */}
                {hasMoreHistory && !isLoadingHistory && messages.length > 0 && (
                    <div className="py-3 text-center text-muted-foreground/50 text-xs">
                        {t("chat.scrollToLoadMore")}
                    </div>
                )}

                {/* Empty State */}
                {messages.length === 0 && !isLoadingHistory && (
                    <ChatWelcome />
                )}

                {/* Message List */}
                {renderItems.map((msg, index) => (
                    <div key={`${msg.id}-${index}`}>
                        <SmartChatMessageItem
                            msg={msg}
                            isGrouped={false}
                            showAvatar={true}
                            onAddToMemory={onAddToMemory ? (txt) => onAddToMemory(txt) : undefined}
                            onRewind={onRewind ? () => onRewind(msg) : undefined}
                            onRetry={onRetry ? () => onRetry(msg) : undefined}
                            onQuote={() => onQuote?.(msg)}
                            onViewChangeset={onViewChangeset}
                        />
                    </div>
                ))}
            </div>
        </div>
    )
}
