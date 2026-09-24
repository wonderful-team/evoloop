import {Button} from "@evoloop/shared/components/ui/button"
import {Collapsible, CollapsibleContent, CollapsibleTrigger,} from "@evoloop/shared/components/ui/collapsible"
import {motion} from "framer-motion"
import {ChevronRight, Layers, Loader2} from "lucide-react"
import {forwardRef, memo, useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState,} from "react"
import {useTranslation} from "react-i18next"
import {Virtuoso, type VirtuosoHandle} from "react-virtuoso"
import {type Message, SmartChatMessageItem} from "./ChatMessageItem"
import {type GalleryImage, ImageGalleryViewer,} from "./ImageGalleryViewer"
import {collectSessionImages} from "./galleryUtils"
import {ChatWelcome} from "./ChatWelcome"
import {useAgentStore} from "@/stores/agentStore"
import {useChatStore} from "@/stores/chatStore"

interface MessageListProps {
  onAddToMemory?: (
    text: string,
    messageId: string | number,
    isRemembered?: boolean,
  ) => void
  onRewind?: (msg: Message) => void
  onRetry?: (msg: Message) => void
  onQuote?: (msg: Message) => void
  onViewChangeset?: (
    messageId: string | number,
    path?: string,
    diff?: string,
  ) => void
  footer?: React.ReactNode
  /** Render these messages instead of the session's (e.g. subagent detail view) */
  overrideMessages?: Message[]
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

function isTaskProposalMessage(msg: Message) {
  const input = msg.input as Record<string, unknown> | undefined
  return (
    msg.role === "tool" &&
    msg.tool_name === "tasks" &&
    input?.action === "create" &&
    input?.source === "agent"
  )
}

const TurnStepsGroupView = memo(function TurnStepsGroupView({
  steps,
  isTurnActive,
  onAddToMemory,
  onRewind,
  onRetry,
  onQuote,
  onViewChangeset,
  onOpenImageGallery,
}: {
  steps: (Message & { showDate?: boolean })[]
  isTurnActive?: boolean
  onAddToMemory?: (
    text: string,
    messageId: string | number,
    isRemembered?: boolean,
  ) => void
  onRewind?: (msg: Message) => void
  onRetry?: (msg: Message) => void
  onQuote?: (msg: Message) => void
  onViewChangeset?: (
    messageId: string | number,
    path?: string,
    diff?: string,
  ) => void
  onOpenImageGallery?: (ref: {
    type: string
    target_id: string
    target_name?: string
  }) => void
}) {
  const { t } = useTranslation()
  const [isOpen, setIsOpen] = useState(isTurnActive || false)

  // 【决定】自动折叠逻辑暂时注释：实测会导致滚动条在流式/折叠瞬间跳来跳去。
  // 保持"思考与执行过程"始终展开，滚动跟随最稳定。
  // 待后续优化折叠时机与滚动配合后再恢复。
  // useEffect(() => {
  //   // 展开立即执行；折叠延时 3 秒，让流式内容先稳定、滚动条先贴底，
  //   // 避免折叠瞬间的高度骤减与滚动跟随抢跑（导致滚动条被顶上去）。
  //   if (isTurnActive) {
  //     setIsOpen(true)
  //     return
  //   }
  //   const timer = setTimeout(() => setIsOpen(false), 3000)
  //   return () => clearTimeout(timer)
  // }, [isTurnActive])

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
          className="group h-6 px-2 rounded text-[11px] font-medium text-muted-foreground/70 hover:text-foreground hover:bg-muted/40 transition-colors flex items-center gap-2 mb-1"
        >
          <Layers className="w-3 h-3 text-muted-foreground/50 group-hover:text-primary/70 shrink-0 transition-colors" />
          <span className="font-mono text-[10px] tracking-[0.08em]">
            {t("chat.interface.executionSteps")}
          </span>
          <span className="font-mono text-[10px] text-muted-foreground/40">
            {steps.length}
          </span>
          <ChevronRight className="w-3 h-3 transition-transform duration-200 group-data-[state=open]:rotate-90 text-muted-foreground/40 ml-0.5" />
        </Button>
      </CollapsibleTrigger>
      <CollapsibleContent className="pl-2 my-1 ml-1.5 border-l border-border/25 space-y-0.5">
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
            onOpenImageGallery={onOpenImageGallery}
          />
        ))}
      </CollapsibleContent>
    </Collapsible>
  )
})

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
          <span className="text-xs">{t("chat.loadingHistory")}</span>
        </div>
      )}
      {hasMoreHistory && !isLoadingHistory && messagesLength > 0 && (
        <div className="py-3 text-center text-muted-foreground/50 text-xs">
          {t("chat.scrollToLoadMore")}
        </div>
      )}
    </>
  )
}

const VirtuosoFooter = ({ context }: any) => {
  const { footer, showTypingIndicator, t } = context || {}
  return (
    <div className="pb-2 px-3 sm:px-5 lg:px-6">
      {showTypingIndicator && (
        <div className="flex items-center gap-2 py-2 text-sm text-muted-foreground">
          <span className="flex gap-1">
            <span className="h-1.5 w-1.5 animate-bounce rounded-full bg-muted-foreground/60 [animation-delay:0ms]" />
            <span className="h-1.5 w-1.5 animate-bounce rounded-full bg-muted-foreground/60 [animation-delay:150ms]" />
            <span className="h-1.5 w-1.5 animate-bounce rounded-full bg-muted-foreground/60 [animation-delay:300ms]" />
          </span>
          {t ? t("chat.typingIndicator") : null}
        </div>
      )}
      {footer}
    </div>
  )
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
  overrideMessages,
}: MessageListProps) {
  const { t } = useTranslation()
  const storeMessages = useChatStore((s) => s.messages)
  const storeHasMoreHistory = useChatStore((s) => s.hasMoreHistory)
  const storeIsLoadingHistory = useChatStore((s) => s.isLoadingHistory)
  const loadMoreHistory = useChatStore((s) => s.loadMoreHistory)
  const messages = overrideMessages ?? storeMessages
  const hasMoreHistory = overrideMessages ? false : storeHasMoreHistory
  const isLoadingHistory = overrideMessages ? false : storeIsLoadingHistory

  // 会话级图片 Gallery：跨消息收集全部图片引用（去重，按消息顺序）
  const [gallery, setGallery] = useState<{
    images: GalleryImage[]
    index: number
  } | null>(null)
  const handleOpenImageGallery = useCallback(
    (ref: { type: string; target_id: string; target_name?: string }) => {
      if (ref.type !== "image" || !ref.target_id) return
      const images = collectSessionImages(messages)
      if (images.length === 0) return
      const idx = Math.max(
        images.findIndex((im) => im.url === ref.target_id),
        0,
      )
      setGallery({ images, index: idx })
    },
    [messages],
  )
  // latest-ref：memo 化的旧消息组件闭包里始终持有同一个稳定引用，
  // 调用时转发到最新实现（否则第一轮消息只能看到旧快照里的图片集）
  const galleryOpenerRef = useRef(handleOpenImageGallery)
  galleryOpenerRef.current = handleOpenImageGallery
  const stableOpenImageGallery = useCallback(
    (ref: {
      type: string
      target_id: string
      target_name?: string
    }) => galleryOpenerRef.current(ref),
    [],
  )
  const galleryUI = (
    <ImageGalleryViewer
      images={gallery?.images || []}
      index={gallery?.index || 0}
      open={!!gallery}
      onIndexChange={(index) => setGallery((g) => (g ? { ...g, index } : g))}
      onClose={() => setGallery(null)}
    />
  )

  // “处理中”占位：Agent 运行中但列表里还没有任何 streaming/running 行
  // （路由/上下文装配/工具首跳期间 LLM 尚未出 token）→ 底部显示思考指示器
  const agentWorking = useAgentStore(
    (s) => s.status === "running" || s.status === "summarizing",
  )
  const showTypingIndicator =
    !overrideMessages &&
    agentWorking &&
    !messages.some(
      (m) =>
        m.status === "streaming" ||
        m.status === "running" ||
        m.status === "pending",
    )
  const scrollerRef = useRef<HTMLElement | null>(null)
  const virtuosoRef = useRef<VirtuosoHandle>(null)
  // Use refs to avoid stale closures in Virtuoso callbacks
  const callbacksRef = useRef({
    hasMoreHistory,
    isLoadingHistory,
    loadMoreHistory,
  })
  // One-shot flag: force the next followOutput to pin to the bottom (used
  // right after sending a message / clicking retry). Afterwards we hand control
  // back to Virtuoso's native followOutput, which already implements the
  // desired interaction: follow while at the bottom, stop when the user scrolls
  // up, resume when they scroll back to the bottom.
  const forceFollowRef = useRef(false)
  // Tracks whether the user has DELIBERATELY scrolled up (to stop following).
  // Crucially we do NOT gate following on "is the viewport exactly at the
  // bottom right now": during fast SSE streaming the scrollTop can transiently
  // lag behind scrollHeight, which would flip an "at bottom" flag off and
  // permanently stop following (the deadlock you saw — content grows, the bar
  // is pushed up and never recovers). Instead we only stop following on an
  // actual upward scroll by the user, and resume once they scroll back down.
  const userScrolledUpRef = useRef(false)
  const prevScrollTopRef = useRef<number | null>(null)
  const prevScrollHeightRef = useRef<number | null>(null)
  // Tracks the virtual index of the first rendered item so Virtuoso can
  // preserve scroll position when older history is prepended (loadMoreHistory).
  const [firstItemIndex, setFirstItemIndex] = useState(0)
  const prevLenRef = useRef(0)
  const prevFirstIdRef = useRef<string | null>(null)
  const loadMoreTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  useEffect(() => {
    callbacksRef.current = { hasMoreHistory, isLoadingHistory, loadMoreHistory }
  })

  // Detect history prepends (loadMoreHistory adds items at the front) and bump
  // firstItemIndex accordingly, so Virtuoso keeps the visible position instead
  // of jumping when older messages arrive above the current ones. Runs before
  // paint (useLayoutEffect) to avoid a one-frame visual flash.
  useLayoutEffect(() => {
    const firstId = messages.length ? String(messages[0].id) : null
    const prevLen = prevLenRef.current
    const prevFirstId = prevFirstIdRef.current
    prevLenRef.current = messages.length
    prevFirstIdRef.current = firstId
    if (messages.length === 0) {
      // Thread switched / list reset.
      setFirstItemIndex(0)
      return
    }
    // A prepend is only recognized when the previous first item is still
    // present at the exact offset — guards against full-list replacements.
    const delta = messages.length - prevLen
    const oldFirstPreserved =
      prevLen > 0 && delta > 0 && String(messages[delta]?.id) === prevFirstId
    if (delta > 0 && firstId !== prevFirstId && oldFirstPreserved) {
      setFirstItemIndex((v) => v + delta)
    } else if (prevLen > 0 && firstId !== prevFirstId) {
      // Full replacement (e.g. retry/rewind refetch rebuilds the list from the
      // latest page) — restart the virtual index from the fresh first item.
      setFirstItemIndex(0)
    }
  }, [messages])

  // Clean up any pending scroll-triggered load timer on unmount.
  useEffect(() => {
    return () => {
      if (loadMoreTimerRef.current) clearTimeout(loadMoreTimerRef.current)
    }
  }, [])

  // 监听用户强制滚到底部的事件 (比如发送新消息、点击重试)
  useEffect(() => {
    const handleScrollToBottom = () => {
      // Re-engage following (send/retry), then scroll via Virtuoso's own
      // index-based API. No manual scrollTop writes that could race with the
      // list rebuild after a retry refetch.
      userScrolledUpRef.current = false
      prevScrollTopRef.current = null
      prevScrollHeightRef.current = null
      forceFollowRef.current = true
      virtuosoRef.current?.scrollToIndex({
        index: "LAST",
        align: "end",
        behavior: "auto",
      })
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
          if (
            scrollableHeight <= 0 ||
            (scrollableHeight > 0 && scrollTop / scrollableHeight <= 0.2)
          ) {
            loadMoreHistory?.()
          }
        }
      }, 50)
      return () => clearTimeout(timer)
    }
  }, [isLoadingHistory, hasMoreHistory, loadMoreHistory])

  const handleFollowOutput = useCallback((isAtBottom: boolean) => {
    // Follow while the user has not deliberately scrolled up. We deliberately
    // ignore isAtBottom for the decision (except as a Virtuoso hint) so a
    // transient lag during streaming never permanently detaches the viewport.
    if (userScrolledUpRef.current) return false
    // forceFollowRef (send/retry) pins immediately regardless of position.
    if (forceFollowRef.current) {
      forceFollowRef.current = false
      return "smooth"
    }
    return isAtBottom ? "auto" : "smooth"
  }, [])

  const handleScroll = useCallback((event: React.UIEvent) => {
    const target = event.target as HTMLElement
    const { scrollTop, scrollHeight, clientHeight } = target
    const prev = prevScrollTopRef.current
    const prevHeight = prevScrollHeightRef.current
    prevScrollTopRef.current = scrollTop
    prevScrollHeightRef.current = scrollHeight
    // A deliberate upward scroll by the user: scrollTop decreased AND the
    // content height did NOT shrink at the same time. A retry/refetch rebuild
    // shortens the list, which makes the browser clamp scrollTop down (smaller)
    // together with scrollHeight — that is NOT a user scroll and must not turn
    // off following, otherwise the viewport stays detached forever.
    if (
      prev !== null &&
      prevHeight !== null &&
      scrollTop < prev &&
      scrollHeight >= prevHeight
    ) {
      userScrolledUpRef.current = true
    }
    // Resume following when the user scrolls back to the bottom. Only when
    // there is actually scrollable content (scrollHeight > clientHeight);
    // otherwise (no overflow) the position check is meaningless.
    const scrollable = scrollHeight - clientHeight
    if (
      userScrolledUpRef.current &&
      scrollable > 0 &&
      scrollTop + clientHeight >= scrollHeight - 24
    ) {
      userScrolledUpRef.current = false
    }

    const scrollableHeight = scrollHeight - clientHeight
    if (scrollableHeight <= 0) return

    if (scrollTop / scrollableHeight > 0.2) return

    // Debounce: coalesce rapid scroll events into a single load.
    if (loadMoreTimerRef.current) return
    const { hasMoreHistory, isLoadingHistory, loadMoreHistory } =
      callbacksRef.current
    if (hasMoreHistory && !isLoadingHistory && loadMoreHistory) {
      loadMoreTimerRef.current = setTimeout(() => {
        loadMoreTimerRef.current = null
        loadMoreHistory()
      }, 150)
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
            // 只要当前 AI 后面还有任何消息（比如正在执行的 tool），它就不是本轮最终输出
            const isFinalInTurn = j === turnMsgs.length - 1
            flushPendingAi(isFinalInTurn)
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
      } else if (msg.role === "system") {
        // ErrorEmitter 单出口：系统级错误块独立成行（不被 turn 分组吞掉，
        // 错误语义打断当前 turn——其后内容归新 turn）。非 error 的 system
        // 在 ChatMessageItem 中仍 return null。
        flushTurn()
        items.push({ type: "message", data: { ...msg } })
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
                ? `${diffSec.toFixed(1)}${t("common.second")}`
                : `${Math.round(endMs - startMs)}${t("common.millisecond")}`
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
          (item.data.tool_name === "ask_human" ||
            item.data.tool_name === "ask_confirm")
        const isTaskProposal = isTaskProposalMessage(item.data)
        if (isTaskProposal) {
          if (currentTurnSteps.length > 0) {
            groupedItems.push({
              type: "turn_steps_group",
              id: `steps_group_before_task_${item.data.id}`,
              steps: currentTurnSteps,
              isTurnActive: false,
            })
            currentTurnSteps = []
          }
          groupedItems.push(item)
        } else if (!isHitlTool) {
          currentTurnSteps.push(item.data)
        }
      }
    }

    if (currentTurnSteps.length > 0) {
      const isTailActive = currentTurnSteps.some(
        (s: any) =>
          s.status === "streaming" ||
          s.status === "running" ||
          s.status === "pending",
      )

      groupedItems.push({
        type: "turn_steps_group",
        id: `steps_group_tail_${currentTurnSteps[0].id}`,
        steps: currentTurnSteps,
        isTurnActive: isTailActive,
      })
    }

    return groupedItems
  }, [messages, t])

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

  // Pin-to-bottom driven by the LAST RENDERED item.
  //
  // Why a sticky-scroll on the raw scroller instead of Virtuoso's followOutput:
  //  - SSE tokens grow the last AI message in-place (array length unchanged),
  //    so Virtuoso's followOutput (length-only) never fires -> we re-pin here.
  //  - Tool steps grow the tail "turn_steps_group" in place the same way, but
  //    a signature like `content.length` misses them (flat rows, static content).
  //  - scrollToIndex("LAST") computes its target from Virtuoso's internal size
  //    cache, which is updated asynchronously (ResizeObserver). Right after a
  //    step is appended the cache is stale, so the computed target equals the
  //    current scrollTop -> the single re-pin is a no-op and the new step ends
  //    up cut off at the bottom. Reading the real DOM scrollHeight instead is
  //    self-correcting for any growth (AI content, tool steps, meta_data, etc.).
  // We only pin while the user has not deliberately scrolled up, so an
  // up-scrolled user is never yanked to the bottom.
  useLayoutEffect(() => {
    if (virtItems.length === 0) return
    if (userScrolledUpRef.current) return
    const el = scrollerRef.current
    if (!el) return
    const pin = () => {
      if (userScrolledUpRef.current) return
      const tail = virtItems[virtItems.length - 1]
      void tail
      el.scrollTop = el.scrollHeight
    }
    pin()
    // rAF fallback: catch late DOM growth (async step mount, etc.)
    requestAnimationFrame(pin)
  }, [virtItems])

  const virtuosoContext = useMemo(
    () => ({
      scrollerRef,
      handleScroll,
      isLoadingHistory,
      hasMoreHistory,
      messagesLength: messages.length,
      t,
      footer,
      showTypingIndicator: showTypingIndicator,
    }),
    [
      handleScroll,
      isLoadingHistory,
      hasMoreHistory,
      messages.length,
      t,
      footer,
      showTypingIndicator,
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
              onOpenImageGallery={stableOpenImageGallery}
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
              onOpenImageGallery={stableOpenImageGallery}
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
      stableOpenImageGallery,
      virtItems.length,
    ],
  )

  if (messages.length === 0 && !isLoadingHistory) {
    return <ChatWelcome />
  }

  return (
    <>
      <Virtuoso
        ref={virtuosoRef}
        style={{ height: "100%" }}
        data={virtItems}
        firstItemIndex={firstItemIndex}
        itemContent={itemContent}
        followOutput={handleFollowOutput}
        atBottomThreshold={50}
        components={STATIC_COMPONENTS}
        context={virtuosoContext}
      />
      {galleryUI}
    </>
  )
})
