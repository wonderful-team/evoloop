import { Button } from "@evoloop/shared/components/ui/button"
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from "@evoloop/shared/components/ui/collapsible"
import { motion } from "framer-motion"
import { ChevronRight, Layers, Loader2 } from "lucide-react"
import {
  forwardRef,
  memo,
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react"
import { useTranslation } from "react-i18next"
import { Virtuoso, type VirtuosoHandle } from "react-virtuoso"
import { type Message, SmartChatMessageItem } from "./ChatMessageItem"
import { ChatWelcome } from "./ChatWelcome"

interface MessageListProps {
  onAddToMemory?: (text: string) => void
  onRewind?: (msg: Message) => void
  onRetry?: (msg: Message) => void
  onQuote?: (msg: Message) => void
  onViewChangeset?: (
    messageId: string | number,
    path?: string,
    diff?: string,
  ) => void
  footer?: React.ReactNode
}

type RenderItem =
  | { type: "message"; data: Message & { showDate?: boolean } }
  | {
      type: "turn_steps_group"
      id: string
      steps: (Message & { showDate?: boolean })[]
      isTurnActive: boolean
    }
  | {
      type: "tool_group"
      data: { steps: Message[]; showDate?: boolean; id: string }
    }

/** Merge multiple AI messages from the same turn into a single message. */
function mergeAiMessages(msgs: Message[]): Message | null {
  if (msgs.length === 0) return null
  const first = msgs[0]
  const last = msgs[msgs.length - 1]

  const paragraphs = msgs.map((m) => m.content?.trim()).filter(Boolean)

  return {
    ...first,
    content: paragraphs.join("\n\n"),
    thinking:
      msgs
        .map((m) => m.thinking)
        .filter(Boolean)
        .join("\n\n") || undefined,
    status: msgs.some((m) => m.status === "streaming")
      ? "streaming"
      : last.status || "completed",
    changeset_count: msgs.reduce((sum, m) => sum + (m.changeset_count || 0), 0),
    changeset_files: msgs.reduce(
      (all, m) => [...all, ...(m.changeset_files || [])],
      [] as any[],
    ),
    has_file_operations: msgs.some((m) => m.has_file_operations),
    timestamp: last.timestamp || first.timestamp,
    humanRequest: msgs.find((m) => m.humanRequest)?.humanRequest,
    references: msgs.reduce(
      (all, m) => [...all, ...(m.references || [])],
      [] as any[],
    ),
  }
}

const TurnStepsGroupView = memo(function TurnStepsGroupView({
  steps,
  isTurnActive,
  onAddToMemory,
  onRewind,
  onRetry,
  onQuote,
  onViewChangeset,
}: {
  steps: (Message & { showDate?: boolean })[]
  isTurnActive?: boolean
  onAddToMemory?: (text: string) => void
  onRewind?: (msg: Message) => void
  onRetry?: (msg: Message) => void
  onQuote?: (msg: Message) => void
  onViewChangeset?: (
    messageId: string | number,
    path?: string,
    diff?: string,
  ) => void
}) {
  const { t } = useTranslation()
  const [isOpen, setIsOpen] = useState(isTurnActive || false)

  useEffect(() => {
    setIsOpen(isTurnActive || false)
  }, [isTurnActive])

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
            {t("chat.interface.executionSteps", {
              defaultValue: "思考与执行过程",
            })}{" "}
            ({steps.length})
          </span>
          <ChevronRight className="w-3.5 h-3.5 transition-transform duration-200 group-data-[state=open]:rotate-90 text-muted-foreground/50 ml-0.5" />
        </Button>
      </CollapsibleTrigger>
      <CollapsibleContent className="pl-1 my-1 border-l-1 border-border/40 space-y-1">
        {steps.map((stepMsg, index) => (
          <SmartChatMessageItem
            key={stepMsg.id}
            msg={stepMsg}
            isGrouped={true}
            showAvatar={false}
            isActivelyStreaming={
              isTurnActive &&
              index === steps.length - 1 &&
              stepMsg.status === "streaming"
            }
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
})

import { useChatStore } from "@/stores/chatStore"

// --- Static Virtuoso Components ---
const VirtuosoScroller = forwardRef((props: any, ref: any) => {
  const { scrollerRef, handleScroll } = props.context || {}
  return (
    <div
      {...props}
      ref={(node) => {
        if (typeof ref === "function") ref(node)
        else if (ref) (ref as any).current = node
        if (scrollerRef) scrollerRef.current = node
      }}
      onScroll={(e) => {
        props.onScroll?.(e as any)
        if (handleScroll) handleScroll(e as any)
      }}
    />
  )
})
VirtuosoScroller.displayName = "VirtuosoScroller"

const VirtuosoItem = memo(({ children, ...props }: any) => (
  <motion.div
    initial={{ opacity: 0 }}
    animate={{ opacity: 1 }}
    transition={{ duration: 0.2 }}
    {...props}
  >
    {children}
  </motion.div>
))
VirtuosoItem.displayName = "VirtuosoItem"

const VirtuosoHeader = ({ context }: any) => {
  const { isLoadingHistory, hasMoreHistory, messagesLength, t } = context || {}
  return (
    <>
      {isLoadingHistory && (
        <div className="py-4 text-center text-muted-foreground">
          <Loader2 className="w-5 h-5 animate-spin mx-auto mb-2" />
          <span className="text-xs">
            {t ? t("chat.loadingHistory") : "Loading..."}
          </span>
        </div>
      )}
      {hasMoreHistory && !isLoadingHistory && messagesLength > 0 && (
        <div className="py-3 text-center text-muted-foreground/50 text-xs">
          {t ? t("chat.scrollToLoadMore") : "Scroll for more"}
        </div>
      )}
    </>
  )
}

const VirtuosoFooter = ({ context }: any) => {
  const { footer } = context || {}
  return <div className="pb-2 px-3 sm:px-5 lg:px-6">{footer}</div>
}

const STATIC_COMPONENTS = {
  Scroller: VirtuosoScroller,
  Item: VirtuosoItem,
  Header: VirtuosoHeader,
  Footer: VirtuosoFooter,
}
// ------------------------------------

export const MessageList = memo(function MessageList({
  onAddToMemory,
  onRewind,
  onRetry,
  onQuote,
  onViewChangeset,
  footer,
}: MessageListProps) {
  const { t } = useTranslation()
  const messages = useChatStore((s) => s.messages)
  const hasMoreHistory = useChatStore((s) => s.hasMoreHistory)
  const isLoadingHistory = useChatStore((s) => s.isLoadingHistory)
  const loadMoreHistory = useChatStore((s) => s.loadMoreHistory)
  const scrollerRef = useRef<HTMLElement | null>(null)
  const virtuosoRef = useRef<VirtuosoHandle>(null)
  // Use refs to avoid stale closures in Virtuoso callbacks
  const callbacksRef = useRef({
    hasMoreHistory,
    isLoadingHistory,
    loadMoreHistory,
  })
  // Flag that forces followOutput to return "auto" once, used after sending a message
  const forceFollowRef = useRef(false)
  useEffect(() => {
    callbacksRef.current = { hasMoreHistory, isLoadingHistory, loadMoreHistory }
  })

  // 监听用户强制滚到底部的事件 (比如发送新消息、点击重试)
  useEffect(() => {
    const handleScrollToBottom = () => {
      // 设置强制跟随标志，使 followOutput 在下次触发时无条件返回 "auto"
      forceFollowRef.current = true
      // 多轮延迟滚动，覆盖 Virtuoso 刚渲染、流式消息高度突变等场景
      const delays = [50, 200, 500, 1000]
      for (const delay of delays) {
        setTimeout(() => {
          virtuosoRef.current?.scrollToIndex({
            index: "LAST",
            align: "end",
            behavior: "auto",
          })
        }, delay)
      }
    }
    window.addEventListener("chat-scroll-to-bottom", handleScrollToBottom)
    return () =>
      window.removeEventListener("chat-scroll-to-bottom", handleScrollToBottom)
  }, [])

  // 自动加载探测：当停止加载且还有历史时，如果滚动条仍在顶部 20% 范围内，或者内容太少无法滚动，则继续触发加载
  useEffect(() => {
    if (!isLoadingHistory && hasMoreHistory) {
      // 给 DOM 渲染一点时间，确保 scrollTop 和 scrollHeight 已经是最新的
      const timer = setTimeout(() => {
        const target = scrollerRef.current
        if (target) {
          const { scrollTop, scrollHeight, clientHeight } = target
          const scrollableHeight = scrollHeight - clientHeight
          if (scrollableHeight <= 0 || (scrollableHeight > 0 && scrollTop / scrollableHeight <= 0.2)) {
            loadMoreHistory?.()
          }
        }
      }, 50)
      return () => clearTimeout(timer)
    }
  }, [isLoadingHistory, hasMoreHistory, loadMoreHistory])

  const handleFollowOutput = useCallback(
    (isAtBottom: boolean) => {
      if (isLoadingHistory) return false
      // 如果有强制跟随标志（用户刚发了消息），无视 isAtBottom，强制跟随并清除标志
      if (forceFollowRef.current) {
        forceFollowRef.current = false
        return "auto"
      }
      if (!isAtBottom) return false
      return "auto"
    },
    [isLoadingHistory],
  )

  const handleScroll = useCallback((event: React.UIEvent) => {
    const target = event.target as HTMLElement
    const { scrollTop, scrollHeight, clientHeight } = target
    const scrollableHeight = scrollHeight - clientHeight
    if (scrollableHeight <= 0) return

    if (scrollTop / scrollableHeight > 0.2) return

    const { hasMoreHistory, isLoadingHistory, loadMoreHistory } =
      callbacksRef.current
    if (hasMoreHistory && !isLoadingHistory && loadMoreHistory) {
      loadMoreHistory()
    }
  }, [])

  const renderItems = useMemo(() => {
    // ─── 第一步：把消息列表拍平成 items ───────────────────────────────────────
    // 规则：
    //   human  → 直接入 items
    //   ai     → 连续多条 ai 合并成一条（mergeAiMessages），遇到 tool/human 才 flush
    //   tool   → 直接入 items（不触发 ai 组 flush，让 ai 组跨越 tool 边界）
    //
    // 注意：ai 组 flush 只在 human 或结束时触发，tool 消息不打断 ai 合并，
    // 这样就避免了"每次 AI→tool→AI 边界产生新分组"的问题。
    const items: {
      type: "message"
      data: Message & {
        showDate?: boolean
        isFirstInTurn?: boolean
        isLastInTurn?: boolean
        turnDuration?: string
      }
    }[] = []
    let prevTimestamp: string | undefined

    // 收集当前轮次中所有待处理的消息（包括 ai 和 tool 交替）
    // 我们改为按"turn"（两个 human 之间）来处理，而不是按 ai 分组
    let turnMsgs: Message[] = []

    const flushTurn = () => {
      if (turnMsgs.length === 0) return

      let isFirstAiInTurn = true
      let pendingAiGroup: Message[] = []

      const flushPendingAi = (isFinalInTurn: boolean) => {
        if (pendingAiGroup.length === 0) return
        const merged = mergeAiMessages(pendingAiGroup)
        if (merged) {
          const showDate =
            !!merged.timestamp &&
            (!prevTimestamp ||
              new Date(merged.timestamp).toDateString() !==
                new Date(prevTimestamp).toDateString())
          items.push({
            type: "message",
            data: {
              ...merged,
              showDate,
              isFirstInTurn: isFirstAiInTurn,
              // 只有 turn 内最后一段 AI 才标记 isLastInTurn
              ...(isFinalInTurn ? { isLastInTurn: true } : {}),
            } as any,
          })
          prevTimestamp = merged.timestamp
          isFirstAiInTurn = false
        }
        pendingAiGroup = []
      }

      for (let j = 0; j < turnMsgs.length; j++) {
        const m = turnMsgs[j]
        if (m.role === "ai") {
          pendingAiGroup.push(m)
          // 如果下一条不是 ai（tool 或结束），先 flush
          const nextM = turnMsgs[j + 1]
          if (!nextM || nextM.role !== "ai") {
            const hasMoreAiAfter = turnMsgs
              .slice(j + 1)
              .some((m) => m.role === "ai")
            flushPendingAi(!hasMoreAiAfter)
          }
        } else if (m.role === "tool") {
          // tool 消息直接入 items，不打断 ai 组
          const showDate =
            !!m.timestamp &&
            (!prevTimestamp ||
              new Date(m.timestamp).toDateString() !==
                new Date(prevTimestamp).toDateString())
          items.push({
            type: "message",
            data: { ...m, showDate, isFirstInTurn: false } as any,
          })
          prevTimestamp = m.timestamp
        }
      }

      turnMsgs = []
    }

    let isNewAiTurn = true

    for (let i = 0; i < messages.length; i++) {
      const msg = messages[i]

      if (msg.role === "human") {
        flushTurn()
        const showDate =
          !!msg.timestamp &&
          (!prevTimestamp ||
            new Date(msg.timestamp).toDateString() !==
              new Date(prevTimestamp).toDateString())
        items.push({ type: "message", data: { ...msg, showDate } })
        prevTimestamp = msg.timestamp
        isNewAiTurn = true
      } else if (msg.role === "ai" || msg.role === "tool") {
        if (isNewAiTurn && msg.role === "ai") {
          // 标记 turn 内第一条 AI（用于决定是否显示 avatar）
          turnMsgs.push({ ...msg, isFirstInTurn: true } as any)
          isNewAiTurn = false
        } else {
          turnMsgs.push(msg)
        }
      }
    }
    flushTurn()

    // ─── 第二步：计算每个 turn 的 duration 并标记 ─────────────────────────────
    const getItemTimestamp = (itm: any): string | undefined => {
      if (!itm) return undefined
      if (itm.data?.timestamp) return itm.data.timestamp
      return undefined
    }

    let turnStartIndex = 0
    let turnFirstAiIndex = -1
    let turnLastAiIndex = -1
    let lastAiContentInTurn = ""

    const closeTurn = () => {
      if (turnFirstAiIndex !== -1 && lastAiContentInTurn) {
        ;(items[turnFirstAiIndex].data as any).effective_content =
          lastAiContentInTurn
      }
      if (turnLastAiIndex !== -1) {
        const lastAiItem = items[turnLastAiIndex]

        const firstItem = items[turnStartIndex]
        const firstTs = getItemTimestamp(firstItem)
        const lastTs = getItemTimestamp(lastAiItem)
        if (firstTs && lastTs) {
          const startMs = new Date(firstTs).getTime()
          const endMs = new Date(lastTs).getTime()
          if (
            !Number.isNaN(startMs) &&
            !Number.isNaN(endMs) &&
            endMs >= startMs
          ) {
            const diffSec = (endMs - startMs) / 1000
            ;(lastAiItem.data as any).turnDuration =
              diffSec >= 1
                ? `${diffSec.toFixed(1)}s`
                : `${Math.round(endMs - startMs)}ms`
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
        if ((item.data as any).isFirstInTurn) {
          closeTurn()
          turnStartIndex = i
          turnFirstAiIndex = i
          turnLastAiIndex = i
          lastAiContentInTurn = item.data.content || ""
        } else if ((item.data as any).isLastInTurn) {
          turnLastAiIndex = i
          if (item.data.content && item.data.content.trim() !== "") {
            lastAiContentInTurn = item.data.content
          }
        }
      }
    }
    closeTurn()

    // ─── 第三步：把中间步骤归入 turn_steps_group ─────────────────────────────
    // isLastInTurn=true 的 AI 消息触发 group 提交；其余全部进 currentTurnSteps。
    // 整个 turn 内所有中间步骤（多次 AI tool_call + tool_output）共享一个 group，
    // 页面上只呈现一个"思考与执行过程"区域。
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
      } else if ((item.data as any).isLastInTurn) {
        const isStreaming =
          item.data.status === "streaming" ||
          item.data.status === "running" ||
          item.data.status === "pending"

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
          data: { ...item.data, thinking: undefined },
        })
      } else {
        // 中间步骤（AI tool_call、tool_output、未标 isLastInTurn 的 AI 消息）全进 steps
        const isHitlTool =
          item.data.role === "tool" &&
          (item.data.tool_name === "ask_human" || item.data.tool_name === "ask_confirm")
        if (!isHitlTool) {
          currentTurnSteps.push(item.data)
        }
      }
    }

    if (currentTurnSteps.length > 0) {
      // 检查最后一项：如果最后一个是 human，说明剩余步骤属于新的一轮，
      // 不应该合并到上一轮的分组中
      const lastItem = groupedItems[groupedItems.length - 1]
      const isNewTurn =
        lastItem &&
        lastItem.type === "message" &&
        lastItem.data.role === "human"

      if (!isNewTurn) {
        for (let k = groupedItems.length - 1; k >= 0; k--) {
          const last = groupedItems[k]
          if (last.type === "turn_steps_group") {
            last.steps.push(...currentTurnSteps)
            return groupedItems
          }
        }
      }

      groupedItems.push({
        type: "turn_steps_group",
        id: `steps_group_tail_${currentTurnSteps[0].id}`,
        steps: currentTurnSteps,
        isTurnActive: true,
      })
    }

    return groupedItems
  }, [messages])

  // Build flat item list for Virtuoso data
  interface VirtItem {
    key: string
    type: "message" | "turn_steps_group"
    data?: Message & {
      showDate?: boolean
      isFirstInTurn?: boolean
      isLastInTurn?: boolean
      turnDuration?: string
    }
    steps?: (Message & { showDate?: boolean })[]
    isTurnActive?: boolean
  }

  const virtItems = useMemo<VirtItem[]>(() => {
    if (messages.length === 0) return []
    return renderItems
      .map((item) => {
        if (item.type === "message") {
          return {
            key: String(item.data.id),
            type: "message" as const,
            data: item.data,
          }
        }
        // "turn_steps_group" is the only other type produced by the render logic
        if (item.type === "turn_steps_group") {
          return {
            key: item.id,
            type: "turn_steps_group" as const,
            steps: item.steps,
            isTurnActive: item.isTurnActive,
          }
        }
        return null
      })
      .filter(Boolean) as VirtItem[]
  }, [renderItems, messages.length])

  const virtuosoContext = useMemo(
    () => ({
      scrollerRef,
      handleScroll,
      isLoadingHistory,
      hasMoreHistory,
      messagesLength: messages.length,
      t,
      footer,
    }),
    [
      handleScroll,
      isLoadingHistory,
      hasMoreHistory,
      messages.length,
      t,
      footer,
    ],
  )

  const itemContent = useCallback(
    (_index: number, item: VirtItem) => {
      if (item.type === "message" && item.data) {
        return (
          <div className="px-3 sm:px-5 lg:px-6">
            <SmartChatMessageItem
              msg={item.data}
              isGrouped={
                !(item.data as any).isFirstInTurn && item.data.role !== "human"
              }
              showAvatar={
                item.data.role === "human" || (item.data as any).isFirstInTurn
              }
              isActivelyStreaming={
                _index === virtItems.length - 1 &&
                item.data.status === "streaming"
              }
              onAddToMemory={onAddToMemory}
              onRewind={() => onRewind?.(item.data!)}
              onRetry={() => onRetry?.(item.data!)}
              onQuote={() => onQuote?.(item.data!)}
              onViewChangeset={onViewChangeset}
            />
          </div>
        )
      }
      if (item.type === "turn_steps_group" && item.steps) {
        return (
          <div className="px-3 sm:px-5 lg:px-6">
            <TurnStepsGroupView
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
      return null
    },
    [
      onAddToMemory,
      onRewind,
      onRetry,
      onQuote,
      onViewChangeset,
      virtItems.length,
    ],
  )

  if (messages.length === 0 && !isLoadingHistory) {
    return <ChatWelcome />
  }

  return (
    <Virtuoso
      ref={virtuosoRef}
      style={{ height: "100%" }}
      data={virtItems}
      itemContent={itemContent}
      followOutput={handleFollowOutput}
      atBottomThreshold={100}
      components={STATIC_COMPONENTS}
      context={virtuosoContext}
    />
  )
})
