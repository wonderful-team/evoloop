import { useMemo } from "react"
import { useTranslation } from "react-i18next"
import { Loader2 } from "lucide-react"
import { motion, AnimatePresence } from "framer-motion"
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
    onViewChangeset?: (messageId: string | number, path?: string) => void
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
        changeset_files: msgs.reduce((all, m) => [...all, ...(m.changeset_files || [])], [] as any[]),
        has_file_operations: msgs.some((m) => m.has_file_operations),
        timestamp: last.timestamp || first.timestamp,
        humanRequest: msgs.find((m) => m.humanRequest)?.humanRequest,
        references: msgs.reduce((all, m) => [...all, ...(m.references || [])], [] as any[]),
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

        let isNewAiTurn = true

        for (let i = 0; i < messages.length; i++) {
            const msg = messages[i]

            if (msg.role === "human") {
                flushAiGroup()
                const showDate = !!msg.timestamp &&
                    (!prevTimestamp || new Date(msg.timestamp).toDateString() !== new Date(prevTimestamp).toDateString())
                items.push({ type: "message", data: { ...msg, showDate } })
                prevTimestamp = msg.timestamp
                isNewAiTurn = true
            } else if (msg.role === "ai") {
                currentAiGroup.push(msg)
                const nextMsg = messages[i + 1]
                if (!nextMsg || nextMsg.role !== "ai") {
                    const merged = mergeAiMessages(currentAiGroup)
                    if (merged) {
                        const showDate = !!merged.timestamp &&
                            (!prevTimestamp || new Date(merged.timestamp).toDateString() !== new Date(prevTimestamp).toDateString())
                        items.push({
                            type: "message",
                            data: { ...merged, showDate, isFirstInTurn: isNewAiTurn } as any
                        })
                        prevTimestamp = merged.timestamp
                        isNewAiTurn = false
                    }
                    currentAiGroup = []
                }
            } else if (msg.role === "tool") {
                flushAiGroup()
                const showDate = !!msg.timestamp &&
                    (!prevTimestamp || new Date(msg.timestamp).toDateString() !== new Date(prevTimestamp).toDateString())
                items.push({
                    type: "message",
                    data: { ...msg, showDate, isFirstInTurn: isNewAiTurn } as any
                })
                prevTimestamp = msg.timestamp
                // Tool messages do NOT reset isNewAiTurn — the following AI message
                // should still be treated as the start of a new AI turn so its
                // header and action buttons remain visible.
            }
        }

        flushAiGroup()

        // Turn-level pass: For each turn, find the last AI item and attach its content to the turn's first AI item as effective_content. Also mark the last AI item in turn.
        let turnFirstAiIndex = -1
        let turnLastAiIndex = -1
        let lastAiContentInTurn = ""

        for (let i = 0; i < items.length; i++) {
            const item = items[i]
            if (item.type === "message") {
                if (item.data.role === "human") {
                    if (turnFirstAiIndex !== -1 && lastAiContentInTurn) {
                        (items[turnFirstAiIndex].data as any).effective_content = lastAiContentInTurn
                    }
                    if (turnLastAiIndex !== -1) {
                        (items[turnLastAiIndex].data as any).isLastInTurn = true
                    }
                    turnFirstAiIndex = -1
                    turnLastAiIndex = -1
                    lastAiContentInTurn = ""
                } else if (item.data.role === "ai") {
                    if ((item.data as any).isFirstInTurn) {
                        if (turnFirstAiIndex !== -1 && lastAiContentInTurn) {
                            (items[turnFirstAiIndex].data as any).effective_content = lastAiContentInTurn
                        }
                        if (turnLastAiIndex !== -1) {
                            (items[turnLastAiIndex].data as any).isLastInTurn = true
                        }
                        turnFirstAiIndex = i
                        turnLastAiIndex = i
                        lastAiContentInTurn = item.data.content || ""
                    } else {
                        turnLastAiIndex = i
                        if (item.data.content && item.data.content.trim() !== "") {
                            lastAiContentInTurn = item.data.content
                        }
                    }
                }
            }
        }
        if (turnFirstAiIndex !== -1 && lastAiContentInTurn) {
            (items[turnFirstAiIndex].data as any).effective_content = lastAiContentInTurn
        }
        if (turnLastAiIndex !== -1) {
            (items[turnLastAiIndex].data as any).isLastInTurn = true
        }

        return items
    }, [messages])

    return (
        <div className="min-h-0 min-w-0 relative">
            <div className="px-1 pb-2 min-w-0">
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

                <AnimatePresence initial={false}>
                    {renderItems.map((item) => {
                        if (item.type === "message") {
                            return (
                                <motion.div
                                    key={item.data.id}
                                    initial={{ opacity: 0 }}
                                    animate={{ opacity: 1 }}
                                    transition={{ duration: 0.2 }}
                                >
                                    <SmartChatMessageItem
                                        msg={item.data}
                                        isGrouped={!(item.data as any).isFirstInTurn && item.data.role !== "human"}
                                        showAvatar={item.data.role === "human" || (item.data as any).isFirstInTurn}
                                        onAddToMemory={onAddToMemory}
                                        onRewind={() => onRewind?.(item.data)}
                                        onRetry={() => onRetry?.(item.data)}
                                        onQuote={() => onQuote?.(item.data)}
                                        onViewChangeset={onViewChangeset}
                                    />
                                </motion.div>
                            )
                        }
                        return null
                    })}
                </AnimatePresence>
            </div>
        </div>
    )
}
