import { useMemo } from "react"
import { useTranslation } from "react-i18next"
import { Loader2 } from "lucide-react"
import { SmartChatMessageItem, type Message } from "./ChatMessageItem"
import { PendingMessageItem } from "./PendingMessageItem"
import { ChatWelcome } from "./ChatWelcome"

interface MessageListProps {
    messages: Message[]
    isAgentWorking: boolean
    hasMoreHistory?: boolean
    isLoadingHistory?: boolean
    onAddToMemory?: (text: string) => void
    onRewind?: (msg: Message) => void
    onRetry?: (msg: Message) => void
    onQuote?: (msg: Message) => void
    onViewChangeset?: () => void // Callback when user clicks to view changeset
}

export function MessageList({
    messages,
    isAgentWorking,
    hasMoreHistory = false,
    isLoadingHistory = false,
    onAddToMemory,
    onRewind,
    onRetry,
    onQuote,
    onViewChangeset,
}: MessageListProps) {
    const { t } = useTranslation()
    // Note: Scroll state is now managed by the parent ChatInterface component

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

    // Note: Scroll handling (infinite scroll & auto-scroll) is now managed by the parent ChatInterface component

    return (
        <div 
            className="min-h-0 min-w-0 relative" 
        >
            <div className="space-y-6 px-4 sm:px-6 lg:px-8 pb-4 min-w-0">
                
                {/* Loading Indicator at Top */}
                {isLoadingHistory && (
                    <div className="py-4 text-center text-muted-foreground">
                        <Loader2 className="w-5 h-5 animate-spin mx-auto mb-2" />
                        <span className="text-xs">{t("chat.loadingHistory")}</span>
                    </div>
                )}

                {/* Load More Hint - shown when there are more messages to load */}
                {hasMoreHistory && !isLoadingHistory && (
                    <div className="py-3 text-center text-muted-foreground/50 text-xs">
                        {t("chat.scrollToLoadMore")}
                    </div>
                )}

                {/* Empty State */}
                {messages.length === 0 && !isLoadingHistory && (
                    <ChatWelcome />
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

                        <SmartChatMessageItem
                            msg={msg}
                            isGrouped={msg.isGrouped}
                            showAvatar={msg.showAvatar}
                            onAddToMemory={onAddToMemory ? (txt) => onAddToMemory(txt) : undefined}
                            onRewind={onRewind ? () => onRewind(msg) : undefined}
                            onRetry={onRetry ? () => onRetry(msg) : undefined}
                            onQuote={() => onQuote?.(msg)}
                            onViewChangeset={onViewChangeset}
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
