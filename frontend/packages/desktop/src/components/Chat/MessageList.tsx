import { useMemo } from "react"
import { useTranslation } from "react-i18next"
import { Loader2 } from "lucide-react"
import { SmartChatMessageItem, type Message } from "./ChatMessageItem"
import type { ToolStep } from "@/types/toolstep"
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

/** Extract a human-readable param from a tool step's input. */
function extractStepParam(step: ToolStep): string {
    const input = step.input
    if (!input || typeof input !== "object") return ""
    const keys = step.tool_meta?.affected_path_keys
    if (keys && keys.length > 0) {
        for (const key of keys) {
            const val = (input as Record<string, any>)[key]
            if (val != null && val !== "") return String(val)
        }
    }
    const skipFields = ["Mode", "TaskName", "TaskStatus"]
    for (const [key, val] of Object.entries(input)) {
        if (skipFields.includes(key)) continue
        if (typeof val === "string" && val) return val
        if (typeof val === "number") return String(val)
    }
    return ""
}

/** Format steps into a plain-text summary line. */
function formatStepSummary(steps: ToolStep[]): string {
    if (!steps || steps.length === 0) return ""
    return steps
        .map((step) => {
            const name = step.tool_meta?.display_name || step.name || step.tool_name || step.tool || ""
            const param = extractStepParam(step)
            return param ? `${name}：${param}` : name
        })
        .filter(Boolean)
        .join("，")
}

/** Merge multiple AI messages from the same turn into a single message.
 *  Each AI message's content is followed by its step summary inline.
 *  Steps are cleared after embedding to avoid duplicate rendering.
 */
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
        steps: msgs.flatMap((m) => m.steps || []), // Preserve all steps for structured rendering
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
    // A turn = one human message + all consecutive AI messages that follow it.
    const turns = useMemo(() => {
        const result: Turn[] = []
        let currentAi: Message[] = []

        for (const msg of messages) {
            if (msg.role === "human") {
                if (currentAi.length > 0) {
                    if (result.length > 0) {
                        result[result.length - 1].ai = currentAi
                    } else {
                        result.push({ ai: currentAi })
                    }
                    currentAi = []
                }
                result.push({ human: msg, ai: [] })
            } else if (msg.role === "ai") {
                currentAi.push(msg)
            }
        }

        if (currentAi.length > 0) {
            if (result.length > 0) {
                result[result.length - 1].ai = currentAi
            } else {
                result.push({ ai: currentAi })
            }
        }

        return result
    }, [messages])

    // Build render items: each turn produces 1 human bubble + 1 merged AI bubble.
    const renderItems = useMemo(() => {
        const items: (Message & { showDate?: boolean })[] = []
        let prevTimestamp: string | undefined

        for (const turn of turns) {
            // Human message
            if (turn.human) {
                const showDate = !!turn.human.timestamp &&
                    (!prevTimestamp || new Date(turn.human.timestamp).toDateString() !== new Date(prevTimestamp).toDateString())
                items.push({ ...turn.human, showDate })
                prevTimestamp = turn.human.timestamp
            }

            // Merged AI messages
            const merged = mergeAiMessages(turn.ai)
            if (merged) {
                const showDate = !!merged.timestamp &&
                    (!prevTimestamp || new Date(merged.timestamp).toDateString() !== new Date(prevTimestamp).toDateString())
                items.push({ ...merged, showDate })
                prevTimestamp = merged.timestamp
            }
        }

        return items
    }, [turns])

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
