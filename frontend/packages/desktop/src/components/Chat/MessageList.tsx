import { useMemo, useState } from "react"
import { useTranslation } from "react-i18next"
import { Loader2, Layers, ChevronRight } from "lucide-react"
import { motion, AnimatePresence } from "framer-motion"
import { Button } from "@evoloop/shared/components/ui/button"
import {
    Collapsible,
    CollapsibleContent,
    CollapsibleTrigger
} from "@evoloop/shared/components/ui/collapsible"
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
    | { type: "turn_steps_group"; id: string; steps: (Message & { showDate?: boolean })[] }
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

function TurnStepsGroupView({
    steps,
    onAddToMemory,
    onRewind,
    onRetry,
    onQuote,
    onViewChangeset,
}: {
    steps: (Message & { showDate?: boolean })[]
    onAddToMemory?: (text: string) => void
    onRewind?: (msg: Message) => void
    onRetry?: (msg: Message) => void
    onQuote?: (msg: Message) => void
    onViewChangeset?: (messageId: string | number, path?: string) => void
}) {
    const { t } = useTranslation()
    const [isOpen, setIsOpen] = useState(true)

    return (
        <Collapsible
            open={isOpen}
            onOpenChange={setIsOpen}
            className="w-full my-2 transition-all"
        >
            <CollapsibleTrigger asChild>
                <Button
                    variant="ghost"
                    size="sm"
                    className="group h-7 px-2.5 rounded text-xs font-medium text-muted-foreground hover:text-foreground hover:bg-muted/40 transition-colors flex items-center gap-2 mb-1"
                >
                    <Layers className="w-3.5 h-3.5 text-primary/70 shrink-0" />
                    <span>
                        {t("chat.interface.executionSteps", { defaultValue: "思考与执行过程" })} ({steps.length})
                    </span>
                    <ChevronRight className="w-3.5 h-3.5 transition-transform duration-200 group-data-[state=open]:rotate-90 text-muted-foreground/50 ml-0.5" />
                </Button>
            </CollapsibleTrigger>
            <CollapsibleContent className="pl-1 py-1 ml-3 my-1 border-l-2 border-border/40 space-y-1">
                {steps.map((stepMsg) => (
                    <SmartChatMessageItem
                        key={stepMsg.id}
                        msg={stepMsg}
                        isGrouped={true}
                        showAvatar={false}
                        onAddToMemory={onAddToMemory}
                        onRewind={() => onRewind?.(stepMsg)}
                        onRetry={() => onRetry?.(stepMsg)}
                        onQuote={() => onQuote?.(stepMsg)}
                        onViewChangeset={onViewChangeset}
                    />
                ))}
            </CollapsibleContent>
        </Collapsible>
    )
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
        const items: ({ type: "message"; data: Message & { showDate?: boolean; isFirstInTurn?: boolean; isLastInTurn?: boolean; turnDuration?: string } })[] = []
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
            }
        }

        flushAiGroup()

        // Turn-level pass: Find the last AI item in turn, attach effective_content, mark isLastInTurn and duration.
        const getItemTimestamp = (itm: any): string | undefined => {
            if (!itm) return undefined
            if (itm.data?.timestamp) return itm.data.timestamp
            if (itm.data?.steps?.[0]?.timestamp) return itm.data.steps[0].timestamp
            return undefined
        }

        let turnStartIndex = 0
        let turnFirstAiIndex = -1
        let turnLastAiIndex = -1
        let lastAiContentInTurn = ""

        const closeTurn = () => {
            if (turnFirstAiIndex !== -1 && lastAiContentInTurn) {
                (items[turnFirstAiIndex].data as any).effective_content = lastAiContentInTurn
            }
            if (turnLastAiIndex !== -1) {
                const lastAiItem = items[turnLastAiIndex]
                ;(lastAiItem.data as any).isLastInTurn = true

                const firstItem = items[turnStartIndex]
                const firstTs = getItemTimestamp(firstItem)
                const lastTs = getItemTimestamp(lastAiItem)
                if (firstTs && lastTs) {
                    const startMs = new Date(firstTs).getTime()
                    const endMs = new Date(lastTs).getTime()
                    if (!isNaN(startMs) && !isNaN(endMs) && endMs >= startMs) {
                        const diffSec = (endMs - startMs) / 1000
                        ;(lastAiItem.data as any).turnDuration = diffSec >= 1 ? `${diffSec.toFixed(1)}s` : `${Math.round((endMs - startMs))}ms`
                    }
                }
            }
        }

        for (let i = 0; i < items.length; i++) {
            const item = items[i]
            if (item.data.role === "human") {
                closeTurn()
                turnStartIndex = i
                turnFirstAiIndex = -1
                turnLastAiIndex = -1
                lastAiContentInTurn = ""
            } else if (item.data.role === "ai") {
                if (item.data.isFirstInTurn) {
                    closeTurn()
                    turnStartIndex = i
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
        closeTurn()

        // 步骤 3: 归纳步骤折叠组 (turn_steps_group)，并将最后一条消息中的 thinking 提取到步骤组内部
        const groupedItems: RenderItem[] = []
        let currentTurnSteps: any[] = []

        for (let i = 0; i < items.length; i++) {
            const item = items[i]
            if (item.data.role === "human") {
                if (currentTurnSteps.length > 0) {
                    groupedItems.push({
                        type: "turn_steps_group",
                        id: `steps_group_before_${item.data.id}`,
                        steps: currentTurnSteps,
                    })
                    currentTurnSteps = []
                }
                groupedItems.push(item)
            } else {
                if (item.data.isLastInTurn) {
                    if (item.data.thinking) {
                        currentTurnSteps.push({
                            id: `${item.data.id}_thinking`,
                            role: "ai",
                            thinking: item.data.thinking,
                            timestamp: item.data.timestamp,
                            status: item.data.status,
                        } as any)
                    }

                    if (currentTurnSteps.length > 0) {
                        groupedItems.push({
                            type: "turn_steps_group",
                            id: `steps_group_${item.data.id}`,
                            steps: currentTurnSteps,
                        })
                        currentTurnSteps = []
                    }

                    groupedItems.push({
                        ...item,
                        data: {
                            ...item.data,
                            thinking: undefined,
                        },
                    })
                } else {
                    currentTurnSteps.push(item.data)
                }
            }
        }

        if (currentTurnSteps.length > 0) {
            groupedItems.push({
                type: "turn_steps_group",
                id: `steps_group_tail_${currentTurnSteps[0].id}`,
                steps: currentTurnSteps,
            })
        }

        return groupedItems
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
                        } else if (item.type === "turn_steps_group") {
                            return (
                                <motion.div
                                    key={item.id}
                                    initial={{ opacity: 0 }}
                                    animate={{ opacity: 1 }}
                                    transition={{ duration: 0.2 }}
                                >
                                    <TurnStepsGroupView
                                        steps={item.steps}
                                        onAddToMemory={onAddToMemory}
                                        onRewind={onRewind}
                                        onRetry={onRetry}
                                        onQuote={onQuote}
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
