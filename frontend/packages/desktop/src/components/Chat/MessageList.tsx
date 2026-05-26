import { useMemo, useState, useEffect, forwardRef, useRef } from "react"
import { Virtuoso } from "react-virtuoso"
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
    scrollRef?: React.RefObject<HTMLDivElement | null>
    onScroll?: (e: React.UIEvent<HTMLDivElement>) => void
    footerNode?: React.ReactNode
}

type RenderItem =
    | { type: "message"; data: Message & { showDate?: boolean } }
    | { type: "turn_steps_group"; id: string; steps: (Message & { showDate?: boolean })[]; isTurnActive: boolean }
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

const groupExpandedState = new Map<string, boolean>()

function TurnStepsGroupView({
    id,
    steps,
    isTurnActive,
    onAddToMemory,
    onRewind,
    onRetry,
    onQuote,
    onViewChangeset,
}: {
    id: string
    steps: (Message & { showDate?: boolean })[]
    isTurnActive?: boolean
    onAddToMemory?: (text: string) => void
    onRewind?: (msg: Message) => void
    onRetry?: (msg: Message) => void
    onQuote?: (msg: Message) => void
    onViewChangeset?: (messageId: string | number, path?: string) => void
}) {
    const { t } = useTranslation()
    
    // Initialize state from global map if it exists, otherwise default to active state
    const [isOpen, setIsOpen] = useState(() => {
        if (groupExpandedState.has(id)) {
            return groupExpandedState.get(id)!
        }
        return !!isTurnActive
    })

    // Track the previous active state to detect when SSE generation starts/finishes
    const prevIsTurnActive = useRef(isTurnActive)

    useEffect(() => {
        // Detect transitions in isTurnActive
        if (prevIsTurnActive.current && !isTurnActive) {
            // Generation just finished -> Auto collapse
            setIsOpen(false)
            groupExpandedState.set(id, false)
        } else if (!prevIsTurnActive.current && isTurnActive) {
            // Generation just started -> Auto expand
            setIsOpen(true)
            groupExpandedState.set(id, true)
        }
        prevIsTurnActive.current = isTurnActive
    }, [isTurnActive, id])

    const handleOpenChange = (open: boolean) => {
        setIsOpen(open)
        groupExpandedState.set(id, open)
    }

    return (
        <Collapsible
            open={isOpen}
            onOpenChange={handleOpenChange}
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
            <CollapsibleContent className="pl-1 my-1 border-l-1 border-border/40 space-y-1 overflow-hidden data-[state=closed]:animate-collapsible-up data-[state=open]:animate-collapsible-down">
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

function computeRenderItems(messages: Message[]): RenderItem[] {
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

    // Turn-level pass
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
                    isTurnActive: false,
                })
                currentTurnSteps = []
            }
            groupedItems.push(item)
        } else {
            if (item.data.isLastInTurn) {
                const isStreaming = item.data.status === "streaming" || item.data.status === "running" || item.data.status === "pending"

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
                        isTurnActive: isStreaming,
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
            isTurnActive: true,
        })
    }

    return groupedItems
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
    scrollRef,
    onScroll,
    footerNode,
}: MessageListProps) {
    const { t } = useTranslation()

    // 找到最后一个 human message 的索引，拆分 stable 和 streaming
    const lastHumanIndex = useMemo(() => {
        for (let i = messages.length - 1; i >= 0; i--) {
            if (messages[i].role === "human") {
                return i;
            }
        }
        return 0; // 如果没找到 human，就全部当作 streaming 处理，或者按 0
    }, [messages.length]);

    // 使用长度、最后一个元素的ID和状态作为 stableMessages 的缓存依赖，避免 O(N) 重复执行
    const stableRenderItems = useMemo(() => {
        const stableMessages = messages.slice(0, lastHumanIndex);
        return computeRenderItems(stableMessages);
    }, [
        lastHumanIndex, 
        messages[lastHumanIndex - 1]?.id, 
        messages[lastHumanIndex - 1]?.status
    ]);

    const currentTurnRenderItems = useMemo(() => {
        const streamingMessages = messages.slice(lastHumanIndex);
        return computeRenderItems(streamingMessages);
    }, [messages, lastHumanIndex]);

    const renderItems = useMemo(() => {
        return [...stableRenderItems, ...currentTurnRenderItems];
    }, [stableRenderItems, currentTurnRenderItems]);

    const renderItemContent = (index: number, item: RenderItem) => {
        if (item.type === "message") {
            return (
                <div className="pb-3">
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
                </div>
            )
        } else if (item.type === "turn_steps_group") {
            return (
                <div className="pb-3">
                    <TurnStepsGroupView
                        id={item.id}
                        steps={item.steps}
                        isTurnActive={item.isTurnActive}
                        onAddToMemory={onAddToMemory}
                        onRewind={onRewind}
                        onRetry={onRetry}
                        onQuote={onQuote}
                        onViewChangeset={onViewChangeset}
                    />
                </div>
            )
        }
        return null;
    };

    return (
        <Virtuoso
            data={renderItems}
            itemContent={renderItemContent}
            initialTopMostItemIndex={renderItems.length - 1}
            followOutput="smooth"
            overscan={2000}
            className="w-full"
            style={{ flex: 1 }}
            scrollerRef={(ref) => {
                if (scrollRef) {
                    // Type assertion to bypass readonly ref
                    (scrollRef as any).current = ref;
                }
            }}
            onScroll={onScroll as any}
            components={{
                List: forwardRef((props, ref) => (
                    <div {...props} ref={ref as any} className="px-3 sm:px-5 lg:px-6 pb-1 pt-3 min-w-0 w-full" />
                )),
                Header: () => (
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
                    </div>
                ),
                Footer: () => <div className="min-w-0 w-full">{footerNode}</div>
            }}
        />
    )
}

