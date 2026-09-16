import {
  ResizableHandle,
  ResizablePanel,
  ResizablePanelGroup,
} from "@evoloop/shared/components/ui/resizable"
import {
  Sheet,
  SheetContent,
  SheetHeader,
  SheetTitle,
} from "@evoloop/shared/components/ui/sheet"
import {
  useInfiniteQuery,
  useMutation,
  useQueryClient,
} from "@tanstack/react-query"
import { useLocation } from "@tanstack/react-router"
import { ArrowLeft } from "lucide-react"
import { useCallback, useEffect, useMemo, useRef, useState } from "react"
import { useTranslation } from "react-i18next"
import { toast } from "sonner"
import { AgentService, ConversationsService, MemoryService } from "@/client"
import { isLoggedIn } from "@/hooks/useAuth"
import { useSystemEvent } from "@/hooks/useSystemEvent"
import type { SystemEvent } from "@/lib/SystemSSEClient"
import { safeListen } from "@/lib/tauri"
import { HITL_STATUS } from "@/stores/agent/hitlConstants"
import { useAgentStore } from "@/stores/agentStore"
import { useChangesetStore } from "@/stores/changesetStore"
import { useChatStore } from "@/stores/chatStore"
import { useProjectStore } from "@/stores/projectStore"
import { useUIStore } from "@/stores/uiStore"
import { useUnreadCompletionsStore } from "@/stores/unreadCompletionsStore"
import { ChatInputArea, type ChatInputAreaHandle } from "./ChatInputArea"
import type { Message } from "./ChatMessageItem"
import { ChatSidebar, type Thread } from "./ChatSidebar"
import { ContextPanel } from "./ContextPanel"
import { DebugManager } from "./DebugManager"
import { HITLBanner } from "./HITLBanner"
import { HumanRequestCard } from "./HumanRequestCard"
import { useChatMutations } from "./hooks/useChatMutations"
import { MessageList } from "./MessageList"
import { QuotaExhaustedBanner } from "./QuotaExhaustedBanner"
import { QuotaExhaustedCard } from "./QuotaExhaustedCard"
import { RewindConfirmDialog } from "./RewindConfirmDialog"
import { RunningTasksDock } from "./RunningTasksDock"
import { TerminalCanvas } from "./TerminalCanvas"

// 会话"已完成"的终态集合（后端 run_end / conversation.updated 携带的 status）
const TERMINAL_STATUSES = [
  HITL_STATUS.done,
  HITL_STATUS.failed,
  HITL_STATUS.cancelled,
  HITL_STATUS.completed,
]

// 深链参数（thread_id/message/autoSend/quoteId）——本应用使用 createHashHistory，
// 路由参数会写在 hash（`#/chat?thread_id=x`）里，`window.location.search` 读不到。
// 这里把真实 query 与 hash 内 query 合并，二者皆可取。
const CHAT_LINK_PARAMS = ["quoteId", "message", "autoSend"] as const

function getChatSearchParams(): URLSearchParams {
  const merged = new URLSearchParams(window.location.search)
  const hash = window.location.hash
  const queryAt = hash.indexOf("?")
  if (queryAt !== -1) {
    new URLSearchParams(hash.slice(queryAt + 1)).forEach((value, key) => {
      merged.set(key, value)
    })
  }
  return merged
}

// 清理地址栏中的深链参数，保留路由与其余参数（replaceState 时不要弄丢 hash，
// 否则会直接离开 /chat 页面）。
function stripChatLinkParams() {
  const url = new URL(window.location.href)
  for (const key of CHAT_LINK_PARAMS) url.searchParams.delete(key)
  let newHash = url.hash
  const queryAt = newHash.indexOf("?")
  if (queryAt !== -1) {
    const params = new URLSearchParams(newHash.slice(queryAt + 1))
    for (const key of CHAT_LINK_PARAMS) params.delete(key)
    const remaining = params.toString()
    newHash = remaining
      ? newHash.slice(0, queryAt + 1) + remaining
      : newHash.slice(0, queryAt)
  }
  window.history.replaceState({}, "", `${url.pathname}${url.search}${newHash}`)
}

export function ChatInterface() {
  // --- Store State (selective subscriptions to avoid unnecessary re-renders) ---
  const activeThreadId = useChatStore((s) => s.threadId)
  const storeProjectId = useChatStore((s) => s.projectId)
  const setThread = useChatStore((s) => s.setThread)
  const sendMessage = useChatStore((s) => s.sendMessage)
  const isTerminalMode = useChatStore((s) => s.isTerminalMode)
  const sendTerminalCommand = useChatStore((s) => s.sendTerminalCommand)
  const isSending = useChatStore((s) => s.isSending)
  const status = useAgentStore((s) => s.status)
  const humanRequest = useAgentStore((s) => s.humanRequest)
  const stopAgent = useAgentStore((s) => s.stopAgent)
  const activeSubagentDetail = useAgentStore((s) => s.activeSubagentDetail)
  const activeA2ADetail = useAgentStore((s) => s.activeA2ADetail)
  const markChangeAsViewed = useChangesetStore((s) => s.markChangeAsViewed)
  const markAllChangesAsViewed = useChangesetStore(
    (s) => s.markAllChangesAsViewed,
  )

  const { t } = useTranslation()
  const currentProject = useProjectStore((s) => s.currentProject)
  const isGlobalMode = useProjectStore((s) => s.isGlobalMode)
  const queryClient = useQueryClient()

  // --- Main area tabs: chat | subagent detail | a2a detail ---
  const [mainTab, setMainTab] = useState<"chat" | "subagent" | "a2a">("chat")
  useEffect(() => {
    if (activeSubagentDetail) setMainTab("subagent")
  }, [activeSubagentDetail])
  useEffect(() => {
    if (activeA2ADetail) setMainTab("a2a")
  }, [activeA2ADetail])

  // Leaving to another conversation exits subagent/a2a detail mode.
  useEffect(() => {
    setMainTab("chat")
    useAgentStore.getState()._closeSubagentDetail()
    useAgentStore.getState()._closeA2ADetail()
  }, [activeThreadId])

  const subagents = useAgentStore((s) => s.subagents)
  const activeSubagent = useMemo(
    () => subagents.find((s) => s.subagent_thread_id === activeSubagentDetail),
    [subagents, activeSubagentDetail],
  )
  // Render the subagent detail as a message list inside the chat main area.
  const subagentMessages = useMemo<Message[]>(() => {
    if (!activeSubagent) return []
    const msgs: Message[] = []
    if (activeSubagent.instruction) {
      msgs.push({
        id: `${activeSubagent.subagent_thread_id}-task`,
        role: "human",
        content: activeSubagent.instruction,
        timestamp: new Date().toISOString(),
        status: "completed",
      })
    }
    if (activeSubagent.result) {
      msgs.push({
        id: `${activeSubagent.subagent_thread_id}-result`,
        role: "ai",
        content: activeSubagent.result,
        timestamp: new Date().toISOString(),
        status: "completed",
      })
    }
    if (activeSubagent.error) {
      msgs.push({
        id: `${activeSubagent.subagent_thread_id}-error`,
        role: "ai",
        content: `❌ ${activeSubagent.error}`,
        timestamp: new Date().toISOString(),
        status: "failed",
      })
    }
    return msgs
  }, [activeSubagent])

  const a2aDelegations = useAgentStore((s) => s.a2aDelegations)
  const activeA2A = useMemo(
    () => a2aDelegations.find((d) => d.task_id === activeA2ADetail),
    [a2aDelegations, activeA2ADetail],
  )
  // Render the A2A delegation detail (instruction + remote result) in the main area.
  const a2aMessages = useMemo<Message[]>(() => {
    if (!activeA2A) return []
    const msgs: Message[] = []
    if (activeA2A.instruction) {
      msgs.push({
        id: `${activeA2A.task_id}-task`,
        role: "human",
        content: activeA2A.instruction,
        timestamp: new Date().toISOString(),
        status: "completed",
      })
    }
    if (activeA2A.result) {
      msgs.push({
        id: `${activeA2A.task_id}-result`,
        role: "ai",
        content: activeA2A.result,
        timestamp: new Date().toISOString(),
        status: "completed",
      })
    }
    if (activeA2A.error) {
      msgs.push({
        id: `${activeA2A.task_id}-error`,
        role: "ai",
        content: `❌ ${activeA2A.error}`,
        timestamp: new Date().toISOString(),
        status: "failed",
      })
    }
    return msgs
  }, [activeA2A])

  // --- UI State ---
  const [isRewindDialogOpen, setIsRewindDialogOpen] = useState(false)
  const [_rewindTargetId, _setRewindTargetId] = useState<string | null>(null)
  const [_rewindRevertFiles, _setRewindRevertFiles] = useState(true)
  const [_rewindContent, setRewindContent] = useState("")
  const [confirmMode, setConfirmMode] = useState<"rewind" | "retry">("rewind")
  const [selectedMessageId, setSelectedMessageId] = useState<string | null>(
    null,
  )

  const [rememberingMessageId, setRememberingMessageId] = useState<
    string | number | null
  >(null)

  const chatInputRef = useRef<ChatInputAreaHandle | null>(null)

  // Custom Hook for Mutations
  const { rewindMutation, retryMutation } = useChatMutations({
    setIsRewindDialogOpen,
    chatInputRef,
  })

  const [sidebarActiveTab, setSidebarActiveTab] = useState<string>("chats")
  const [expandAgentChanges, setExpandAgentChanges] = useState<boolean>(false)
  const projectId = currentProject?.id ?? storeProjectId ?? undefined

  // Chat layout state lives in uiStore (shared with the AppTitleBar slot)
  const showChatListSheet = useUIStore((s) => s.showChatListSheet)
  const setShowChatListSheet = useUIStore((s) => s.setShowChatListSheet)
  const showContextPanel = useUIStore((s) => s.showContextPanel)
  const setShowContextPanel = useUIStore((s) => s.setShowContextPanel)
  const isCompactWindow = useUIStore((s) => s.isCompactWindow)
  const showChatList = useUIStore((s) => s.showChatList)

  // Auto-show context panel when switching from global to project mode
  // But only if user hasn't manually closed it (skipped in compact window)
  useEffect(() => {
    const saved = localStorage.getItem("chat.contextPanel.hidden")
    if (
      !isCompactWindow &&
      !isGlobalMode &&
      currentProject &&
      saved !== "true"
    ) {
      setShowContextPanel(true)
    }
  }, [isGlobalMode, currentProject, isCompactWindow])

  // Track if user manually closed context panel during the CURRENT run
  const hasManuallyClosedInCurrentRun = useRef(false)
  // 初始化 effect 只真正跑一次（防止 projectId 解析/切换重复 re-run 拆掉 SSE）
  const initRanRef = useRef(false)
  // 记录最近一次由深链 thread_id 参数选中的会话，用于监听已挂载后的深链跳转
  const lastHandledDeepThreadRef = useRef<string | null>(null)

  // Reset the manual close flag when agent finishes or starts a fresh run
  useEffect(() => {
    if (status !== "running") {
      hasManuallyClosedInCurrentRun.current = false
    }
  }, [status])

  // 审计修复（会话归属错乱）：切换项目 = 切换会话空间。此前 projectId
  // 变化后 threadId 保留旧项目的会话 → 继续往旧 thread 发消息（thread
  // 归属旧项目，会话列表仍出现在旧项目下）。跳过首挂（由 init effect
  // 负责 URL 深链）。
  const lastProjectIdRef = useRef<number | undefined>(undefined)
  useEffect(() => {
    if (lastProjectIdRef.current === undefined) {
      lastProjectIdRef.current = projectId
      return
    }
    if (lastProjectIdRef.current !== projectId) {
      lastProjectIdRef.current = projectId
      setThread(null, projectId ?? null)
    }
  }, [projectId, setThread])

  // Auto-show context panel when agent starts working (skipped in compact window,
  // and skipped when user has manually closed it before)
  useEffect(() => {
    if (
      !isCompactWindow &&
      status === "running" &&
      !showContextPanel &&
      localStorage.getItem("chat.contextPanel.hidden") !== "true" &&
      !hasManuallyClosedInCurrentRun.current
    ) {
      setShowContextPanel(true)
    }
  }, [status, showContextPanel, isCompactWindow])

  // Persist manual close action
  const handleCloseContextPanel = useCallback(() => {
    localStorage.setItem("chat.contextPanel.hidden", "true")
    hasManuallyClosedInCurrentRun.current = true // Mark as manually closed for this run
    setShowContextPanel(false)
  }, [setShowContextPanel])

  // Refresh conversation list when a new conversation is created or an existing
  // one is updated from another device/channel (voice link, mobile, wecom, etc.)
  const handleConversationCreated = useCallback(() => {
    queryClient.invalidateQueries({ queryKey: ["projectConversations"] })
  }, [queryClient])

  const handleConversationUpdated = useCallback(
    (event: SystemEvent) => {
      queryClient.invalidateQueries({ queryKey: ["projectConversations"] })
      // 会话已完成（后端带终态 status）且不是当前激活会话 → 打"已完成"未读点
      const tid = event?.thread_id
      const status = event?.data?.status
      if (tid && TERMINAL_STATUSES.includes(status) && tid !== activeThreadId) {
        useUnreadCompletionsStore.getState().markUnread(tid)
      }
    },
    [queryClient, activeThreadId],
  )

  useSystemEvent("conversation.created", handleConversationCreated)
  useSystemEvent("conversation.updated", handleConversationUpdated)

  // --- Initialization ---
  useEffect(() => {
    if (projectId === undefined) return
    // 只真正的初始化一次：projectId 解析（或后续切换项目）导致的 re-run 不应
    // 再次以 initId 重选会话——那会把正在进行的会话 SSE 流直接 disconnect。
    if (initRanRef.current) return
    initRanRef.current = true

    // Get initial thread ID from URL if present, or create new
    const params = getChatSearchParams()
    const tid = params.get("thread_id")
    const initId = tid && tid.trim() !== "" ? tid : null

    // Check for message intent
    const pendingMessage = params.get("message")
    const shouldAutoSend = params.get("autoSend") === "true"
    const quoteId = params.get("quoteId")

    // Init Store - allow global mode (projectId can be 0)
    setThread(initId, projectId)
    // 首次进入会话（URL 直达）也清除"已完成"未读点
    if (initId) {
      useUnreadCompletionsStore.getState().clearUnread(initId)
    }
    // Small delay to ensure thread is set before sending
    if (pendingMessage) {
      // Clear URL params to prevent re-sending on refresh (Partial clear, wait for quote?)
      // actually we can clear 'message' and 'autoSend' but keep 'quoteId' if we handle it separately?
      // Or just clear all and manage state locally?
      // Let's clear ALL after handling everything.

      // But quote handling depends on messages loading...

      if (shouldAutoSend && !quoteId) {
        // If we have a quoteId, standard autoSend might be too fast before reference is added?
        // Actually, if we just want to PRE-FILL, we shouldn't auto-send immediately if we also want to attach a reference?
        // But the user request said "Jump to conversation... and quote...".
        // If we auto-send, the reference needs to be attached to the message being sent.
        setTimeout(() => sendMessage(pendingMessage), 500)
        stripChatLinkParams()
      } else if (!shouldAutoSend && !quoteId) {
        // 纯预填：消息带入输入框但不自动发送（此前只清 URL，消息被静默丢弃）
        chatInputRef.current?.setInput(pendingMessage)
        stripChatLinkParams()
      }
    }
  }, [projectId, setThread, sendMessage]) // Run once when project loads

  // Handle Quote Deep Link - Dependent on Messages Loading
  useEffect(() => {
    const params = getChatSearchParams()
    const quoteId = params.get("quoteId")
    const pendingMessage = params.get("message")

    if (!quoteId) return

    const checkAndHandleQuote = (currentMessages: any[]) => {
      if (currentMessages.length > 0) {
        const msg = currentMessages.find(
          (m) => m.id === quoteId || m.id.toString() === quoteId,
        )
        if (msg) {
          // Pre-fill input if pending message exists
          if (pendingMessage) {
            chatInputRef.current?.setInput(`${pendingMessage} `)
          }

          // Add reference
          chatInputRef.current?.addReference({
            type: "message",
            id: msg.id.toString(),
            name:
              msg.content.slice(0, 50) +
              (msg.content.length > 50 ? t("common.ellipsis") : ""),
            detail: msg.role,
          })

          // Clear URL
          stripChatLinkParams()
          return true // Handled
        }
      }
      return false
    }

    // Check initially
    if (!checkAndHandleQuote(useChatStore.getState().messages)) {
      // If not found yet, subscribe and wait
      const unsub = useChatStore.subscribe((state) => {
        if (checkAndHandleQuote(state.messages)) {
          unsub()
        }
      })
      return () => unsub()
    }
  }, []) // Run once on mount

  // Handle unauthorized state - trigger global 401 handling (only for logged-in users)
  useEffect(() => {
    if (status === "unauthorized" && isLoggedIn()) {
      console.log("[ChatInterface] Unauthorized status detected")
      // Trigger a dummy API call to trigger the global 401 handler
      // This will show toast and redirect to login
      ConversationsService.listConversations({ projectId: projectId! }).catch(
        () => {
          // Error will be handled by main.tsx's handleApiError
        },
      )
    }
  }, [status, projectId])

  // --- Thread List (Sidebar) ---
  // Kept in React Query as it is a list view concern
  const {
    data: threadsInfiniteData,
    fetchNextPage,
    hasNextPage,
    isFetchingNextPage,
  } = useInfiniteQuery({
    queryKey: ["projectConversations", projectId],
    queryFn: async ({ pageParam = 1 }) => {
      const res = await ConversationsService.listConversations({
        projectId: projectId!,
        page: pageParam,
        pageSize: 20,
      })
      return res
    },
    initialPageParam: 1,
    getNextPageParam: (lastPage) => {
      const currentPage = lastPage.page || 1
      const pageSize = lastPage.page_size || 20
      const total = lastPage.total || 0
      if (currentPage * pageSize < total) {
        return currentPage + 1
      }
      return undefined
    },
    enabled: projectId !== undefined,
  })

  const threads: Thread[] = useMemo(() => {
    if (!threadsInfiniteData) return []
    return threadsInfiniteData.pages.flatMap((page) => {
      const items = page.data || []
      return items.map((t: any) => ({
        ...t,
        updated_at: t.updated_at || new Date().toISOString(),
        status: t.status || "idle",
        is_pinned: !!t.is_pinned,
      }))
    })
  }, [threadsInfiniteData])

  const mappedThreads = useMemo(() => {
    return threads.map((t) => ({
      ...t,
      // Override status if it's the active thread, using reliable store state
      status: t.thread_id === activeThreadId ? status : t.status,
    }))
  }, [threads, activeThreadId, status])

  const handleTogglePin = useCallback(
    async (id: string, isPinned: boolean) => {
      try {
        await ConversationsService.updateConversation({
          threadId: id,
          requestBody: { is_pinned: isPinned },
        })
        queryClient.invalidateQueries({
          queryKey: ["projectConversations", projectId],
        })
        toast.success(
          isPinned
            ? t("chat.sidebar.pinSuccess")
            : t("chat.sidebar.unpinSuccess"),
        )
      } catch (err) {
        console.error(err)
        toast.error(t("chat.sidebar.pinActionFailed"))
      }
    },
    [projectId, queryClient],
  )

  // --- Handlers ---

  const handleNewChat = useCallback(() => {
    if (projectId !== undefined) {
      setThread(null, projectId ?? null)
    }
  }, [projectId, setThread])

  // Wrapper for sendMessage to handle post-send actions
  const handleSendMessage = useCallback(
    async (content: string, pickedFiles?: any[]) => {
      // In terminal mode, route to the PTY command executor instead of chat
      if (isTerminalMode) {
        await sendTerminalCommand(content)
        return
      }

      const isNewThread = useChatStore.getState().messages.length === 0

      const sendPromise = sendMessage(content, pickedFiles)

      // 立即触发滚动到底部（用于已有会话场景）
      window.dispatchEvent(new CustomEvent("chat-scroll-to-bottom"))

      await sendPromise

      // 新会话时，sendMessage 内部会调用 setThread 导致 Virtuoso 重新 mount，
      // 此时需要再次触发滚到底部，确保新消息可见
      if (isNewThread) {
        window.dispatchEvent(new CustomEvent("chat-scroll-to-bottom"))
      }

      // If this was a new thread (first message), refresh the conversation list
      if (isNewThread && projectId !== undefined) {
        queryClient.invalidateQueries({
          queryKey: ["projectConversations", projectId],
        })
      }
    },
    [sendMessage, sendTerminalCommand, isTerminalMode, projectId, queryClient],
  )

  // Handle Evoloop deep link `evoloop://create-task` → fill prompt and auto-send
  useEffect(() => {
    let unlisten: (() => void) | undefined
    safeListen<{
      taskId?: string
      secret?: string
      callbackUrl?: string
      prompt?: string
    }>("evoloop:create-task", (ev) => {
      const prompt = ev.payload?.prompt || ""
      if (!prompt) return
      const meta = {
        taskId: ev.payload?.taskId || "",
        secret: ev.payload?.secret || "",
        callbackUrl: ev.payload?.callbackUrl || "",
      }
      if (meta.taskId) {
        useChatStore.getState().setPendingCreateTask(meta)
      }
      chatInputRef.current?.setInput(prompt)
      setTimeout(() => {
        handleSendMessage(prompt)
      }, 120)
    }).then((fn) => (unlisten = fn))
    return () => {
      if (unlisten) unlisten()
    }
  }, [handleSendMessage])

  const handleDeleteThread = useCallback(
    async (id: string) => {
      try {
        await ConversationsService.deleteConversation({ threadId: id })
        queryClient.invalidateQueries({ queryKey: ["projectConversations"] })
        if (id === activeThreadId) {
          // Switch to next or new
          if (threads.length > 0) {
            const next = threads.find((t) => t.thread_id !== id)
            if (next && projectId) setThread(next.thread_id, projectId)
            else handleNewChat()
          } else {
            handleNewChat()
          }
        }
      } catch (_e) {
        toast.error(t("chat.interface.deleteChatError"))
      }
    },
    [
      activeThreadId,
      threads,
      projectId,
      setThread,
      handleNewChat,
      queryClient,
      t,
    ],
  )

  const handleStopThread = useCallback(
    async (id: string) => {
      // If stopping active, use store action. Else API.
      if (id === activeThreadId) {
        await stopAgent()
      } else {
        await AgentService.stopChat({
          requestBody: { thread_id: id, message: "" },
        })
        toast.info(t("chat.interface.stopAgentSuccess"))
      }
    },
    [activeThreadId, stopAgent, t],
  )

  // --- Side Effect Mutations (Keep here or move to store if generic) ---
  // These are specific to message item actions

  const addToMemoryMutation = useMutation({
    mutationFn: async ({
      text,
      messageId,
    }: {
      text: string
      messageId: string | number
      isRemembered?: boolean
    }) => {
      if (projectId === undefined || projectId === null)
        throw new Error(t("common.noProject"))
      return MemoryService.addConcept({
        projectId,
        requestBody: {
          name: text,
          description: text,
          related_files: [],
          source_message_id: messageId.toString(),
          source_thread_id: activeThreadId || undefined,
          memory_kind: "concept",
        },
      })
    },
    onMutate: async ({ messageId, isRemembered }) => {
      await queryClient.cancelQueries({
        queryKey: ["messages", activeThreadId],
      })
      const previousMessages = queryClient.getQueryData<any[]>([
        "messages",
        activeThreadId,
      ])
      queryClient.setQueryData<any[]>(["messages", activeThreadId], (old) => {
        if (!old) return old
        return old.map((m) =>
          m.id === messageId || m.id.toString() === messageId.toString()
            ? { ...m, is_remembered: !isRemembered }
            : m,
        )
      })
      return { previousMessages }
    },
    onError: (_err, _variables, context) => {
      if (context?.previousMessages) {
        queryClient.setQueryData(
          ["messages", activeThreadId],
          context.previousMessages,
        )
      }
      toast.error(t("chat.interface.addMemoryError"))
    },
    onSuccess: () => {
      toast.success(t("chat.interface.addMemorySuccess"))
      queryClient.invalidateQueries({ queryKey: ["projectMemory"] })
    },
    onSettled: (_data, _err, { messageId }) => {
      setRememberingMessageId((prev) => (prev === messageId ? null : prev))
      queryClient.invalidateQueries({ queryKey: ["messages", activeThreadId] })
    },
  })

  const handleQuoteMessage = useCallback((msg: any) => {
    if (!msg || !msg.id) return
    const quoteText =
      msg.effective_content !== undefined && msg.effective_content.trim() !== ""
        ? msg.effective_content
        : msg.content

    // Construct reference item
    chatInputRef.current?.addReference({
      type: "message",
      id: msg.id.toString(),
      name:
        quoteText.slice(0, 50) +
        (quoteText.length > 50 ? t("common.ellipsis") : ""),
      detail: msg.role,
    })
  }, [])

  const handleQuoteFile = useCallback((file: any) => {
    chatInputRef.current?.addReference({
      type: "file",
      id: file.path,
      name: file.name,
      detail: file.path,
    })
  }, [])

  // Handle view changeset from message snapshot
  const handleViewChangeset = useCallback(
    (_messageId?: string | number, path?: string, diff?: string) => {
      // Switch to files tab
      setSidebarActiveTab("files")
      // Expand Agent Changes panel
      setExpandAgentChanges(true)

      const threadId = activeThreadId
      if (threadId) {
        if (path) {
          if (diff) {
            useUIStore.getState().setPreviewDiff({ path, diff })
          } else {
            // Find the file in the changeset and trigger diff (fallback)
            const file = useChangesetStore
              .getState()
              .changeset.find((f) => f.path === path)
            if (file) {
              useUIStore
                .getState()
                .setPreviewDiff({ path: file.path, diff: file.diff || "" })
            }
          }
          // Mark as viewed
          markChangeAsViewed(path, threadId)
        } else {
          // Mark all as viewed
          markAllChangesAsViewed(threadId)
        }
      }
    },
    [markChangeAsViewed, markAllChangesAsViewed, activeThreadId],
  )

  const handleSetActiveThreadId = useCallback(
    (id: string) => {
      // 切进会话即清除"已完成"未读点
      useUnreadCompletionsStore.getState().clearUnread(id)
      if (projectId !== undefined) setThread(id, projectId)
    },
    [projectId, setThread],
  )

  // 深链跳转（已挂载状态下 thread_id 参数变化，如 TaskDetail → /chat?thread_id=…）
  // 依赖 router location.search：hash 路由下 TanStack 会把 hash 内的 query 解析进来，
  // 参数变化才会触发本 effect；参数被清理/不变时不重置，避免覆盖侧栏手动选择。
  const chatLocation = useLocation()
  const threadIdFromLocation = (() => {
    const p = new URLSearchParams(chatLocation.search)
    const v = p.get("thread_id")
    return v && v.trim() !== "" ? v : null
  })()

  useEffect(() => {
    if (threadIdFromLocation === lastHandledDeepThreadRef.current) return
    lastHandledDeepThreadRef.current = threadIdFromLocation
    if (threadIdFromLocation && projectId !== undefined) {
      handleSetActiveThreadId(threadIdFromLocation)
    }
  }, [threadIdFromLocation, handleSetActiveThreadId, projectId])

  const handleSelectDiff = useCallback((path: string, diff: string) => {
    useUIStore.getState().setPreviewDiff({ path, diff })
  }, [])

  const handleAddToMemory = useCallback(
    (txt: string, messageId: string | number, isRemembered?: boolean) => {
      if (rememberingMessageId === messageId) return
      setRememberingMessageId(messageId)
      addToMemoryMutation.mutate({ text: txt, messageId, isRemembered })
    },
    [addToMemoryMutation, rememberingMessageId],
  )

  const handleRewind = useCallback(
    (msg: any) => {
      const currentMessages = useChatStore.getState().messages
      const index = currentMessages.findIndex((m) => m.id === msg.id)
      const subMessages = currentMessages.slice(index)
      const hasFiles = subMessages.some((m) => m.has_file_operations)

      setSelectedMessageId(msg.id.toString())

      if (msg.role === "human") {
        setRewindContent(msg.content)
      } else {
        setRewindContent("")
      }

      if (hasFiles) {
        setConfirmMode("rewind")
        setIsRewindDialogOpen(true)
      } else {
        rewindMutation.mutate({
          revertFiles: false,
          messageId: msg.id.toString(),
          content: msg.role === "human" ? msg.content : undefined,
        })
      }
    },
    [rewindMutation],
  )

  const handleRetry = useCallback(
    (msg: any) => {
      const currentMessages = useChatStore.getState().messages
      const index = currentMessages.findIndex((m) => m.id === msg.id)
      const subMessages = currentMessages.slice(index + 1)
      const hasFiles = subMessages.some((m) => m.has_file_operations)

      setSelectedMessageId(msg.id.toString())
      if (hasFiles) {
        setConfirmMode("retry")
        setIsRewindDialogOpen(true)
      } else {
        retryMutation.mutate({
          revertFiles: false,
          messageId: msg.id.toString(),
        })
      }
    },
    [retryMutation],
  )

  // Auto-focus input when agent finishes
  useEffect(() => {
    if (status === HITL_STATUS.idle || status === HITL_STATUS.interrupted) {
      chatInputRef.current?.focus()
    }
  }, [status])

  // Deep Linking Listener
  useEffect(() => {
    const handleScrollToRun = (e: CustomEvent<{ runId: string }>) => {
      const runId = e.detail.runId
      const el = document.querySelector(`[data-run-id="${runId}"]`)
      if (el) {
        el.scrollIntoView({ behavior: "smooth", block: "start" })
        el.classList.add("ring-2", "ring-primary/20", "rounded-lg")
        setTimeout(
          () => el.classList.remove("ring-2", "ring-primary/20", "rounded-lg"),
          2000,
        )
      } else {
        toast.info(t("chat.interface.messageNotLoaded"))
      }
    }

    const handleLocateFile = (e: CustomEvent<{ path: string }>) => {
      const path = e.detail.path
      if (path) {
        setSidebarActiveTab("files")
        useUIStore.getState().setLocateFilePath(path)
        // Ensure context panel is shown if needed, or if they meant the left sidebar?
        // Wait, left sidebar is open by default, but if on mobile we might need to open it.
        // But AppSidebar toggle is managed by useSidebar. We'll leave it simple for now.
      }
    }

    window.addEventListener(
      "chat-scroll-to-run" as any,
      handleScrollToRun as any,
    )
    window.addEventListener("locate-file" as any, handleLocateFile as any)
    return () => {
      window.removeEventListener(
        "chat-scroll-to-run" as any,
        handleScrollToRun as any,
      )
      window.removeEventListener("locate-file" as any, handleLocateFile as any)
    }
  }, [setSidebarActiveTab])

  // Keyboard Shortcuts: Esc to Stop Agent
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      // Only trigger if Agent is working and Esc is pressed
      if (
        e.key === "Escape" &&
        (status === "running" || status === "summarizing")
      ) {
        console.log("[ChatInterface] Esc pressed, stopping agent.")
        handleStopThread(activeThreadId || "")
      }
    }

    window.addEventListener("keydown", handleKeyDown)
    return () => window.removeEventListener("keydown", handleKeyDown)
  }, [status, activeThreadId, handleStopThread])

  return (
    <div className="flex flex-col h-full w-full min-w-0 relative bg-background overflow-hidden">
      <ResizablePanelGroup
        direction="horizontal"
        className="h-full w-full min-w-0 overflow-hidden"
      >
        {/* Left Sidebar Panel */}
        {showChatList && (
          <ResizablePanel
            id="chat-list"
            order={1}
            defaultSize={16}
            minSize={15}
            maxSize={40}
            className="hidden lg:block min-w-[100px] overflow-hidden"
          >
            <div
              style={{
                contain: "content",
                height: "100%",
                width: "100%",
                minWidth: 0,
              }}
            >
              <ChatSidebar
                threads={mappedThreads}
                activeThreadId={activeThreadId || ""}
                setActiveThreadId={handleSetActiveThreadId}
                projectId={projectId}
                onDeleteThread={handleDeleteThread}
                onNewChat={handleNewChat}
                onSelectDiff={handleSelectDiff}
                onQuoteFile={handleQuoteFile}
                activeTab={sidebarActiveTab}
                onTabChange={setSidebarActiveTab}
                expandAgentChanges={expandAgentChanges}
                fetchNextPage={fetchNextPage}
                hasNextPage={hasNextPage}
                isFetchingNextPage={isFetchingNextPage}
                onTogglePin={handleTogglePin}
              />
            </div>
          </ResizablePanel>
        )}

        {showChatList && (
          <ResizableHandle
            withHandle
            className="w-px bg-transparent data-[resize-handle-active]:bg-transparent after:bg-transparent hover:after:bg-muted/60 [&>div]:border-transparent [&>div]:bg-muted/50 [&>div]:opacity-0 [&>div]:transition-opacity hover:[&>div]:opacity-100 hover:[&>div]:bg-muted/70"
          />
        )}

        {/* Center Chat Panel */}
        <ResizablePanel
          id="chat-main"
          order={2}
          defaultSize={showContextPanel ? 64 : 84}
          minSize={20}
          className="min-w-0 overflow-hidden"
        >
          <div
            className="flex flex-col h-full relative min-h-0 min-w-0 w-full overflow-hidden"
            style={{ contain: "content" }}
          >
            <HITLBanner />
            <QuotaExhaustedBanner />

            <div
              className="flex-1 min-h-0 min-w-0 w-full flex flex-col"
              data-tour="chat-messages"
            >
              {isTerminalMode ? (
                <TerminalCanvas />
              ) : (
                <>
                  {activeSubagentDetail && (
                    <div className="flex items-center gap-2 px-3 py-1.5 bg-muted/20 shrink-0">
                      <button
                        type="button"
                        onClick={() => {
                          setMainTab("chat")
                          useAgentStore.getState()._closeSubagentDetail()
                        }}
                        className="flex items-center gap-1 text-[11px] px-2 py-1 rounded-md text-muted-foreground hover:text-foreground hover:bg-muted transition-colors"
                      >
                        <ArrowLeft className="h-3.5 w-3.5" />
                        {t("chat.subagentDetailBack")}
                      </button>
                      <span className="text-[11px] font-semibold text-muted-foreground">
                        {t("chat.tabSubagentDetail")}
                      </span>
                    </div>
                  )}
                  <div
                    className={`flex-1 min-h-0 min-w-0 ${
                      mainTab === "chat" ? "" : "hidden"
                    }`}
                  >
                    <MessageList
                      onAddToMemory={handleAddToMemory}
                      onRewind={handleRewind}
                      onRetry={handleRetry}
                      onQuote={handleQuoteMessage}
                      onViewChangeset={handleViewChangeset}
                      footer={
                        <>
                          {status === HITL_STATUS.interrupted &&
                            humanRequest && (
                              <HumanRequestCard request={humanRequest} />
                            )}
                          {status === "quota_exhausted" && (
                            <QuotaExhaustedCard />
                          )}
                        </>
                      }
                    />
                  </div>
                  <div
                    className={`flex-1 min-h-0 min-w-0 ${
                      mainTab === "subagent" ? "" : "hidden"
                    }`}
                  >
                    <MessageList
                      overrideMessages={subagentMessages}
                      onAddToMemory={handleAddToMemory}
                      onRewind={handleRewind}
                      onRetry={handleRetry}
                      onQuote={handleQuoteMessage}
                      onViewChangeset={handleViewChangeset}
                      footer={null}
                    />
                  </div>
                  {activeA2ADetail && (
                    <div className="flex items-center gap-2 px-3 py-1.5 bg-muted/20 shrink-0">
                      <button
                        type="button"
                        onClick={() => {
                          setMainTab("chat")
                          useAgentStore.getState()._closeA2ADetail()
                        }}
                        className="flex items-center gap-1 text-[11px] px-2 py-1 rounded-md text-muted-foreground hover:text-foreground hover:bg-muted transition-colors"
                      >
                        <ArrowLeft className="h-3.5 w-3.5" />
                        {t("chat.a2aDetailBack")}
                      </button>
                      <span className="text-[11px] font-semibold text-muted-foreground">
                        {t("chat.tabA2ADetail")}
                      </span>
                    </div>
                  )}
                  <div
                    className={`flex-1 min-h-0 min-w-0 ${
                      mainTab === "a2a" ? "" : "hidden"
                    }`}
                  >
                    <MessageList
                      overrideMessages={a2aMessages}
                      onAddToMemory={handleAddToMemory}
                      onRewind={handleRewind}
                      onRetry={handleRetry}
                      onQuote={handleQuoteMessage}
                      onViewChangeset={handleViewChangeset}
                      footer={null}
                    />
                  </div>
                </>
              )}
            </div>

            {/* Input Area */}
            {status !== HITL_STATUS.interrupted &&
              status !== "quota_exhausted" &&
              mainTab === "chat" && (
                <>
                  {/* 执行中的命令独立状态条（在工具条/输入框上方） */}
                  <RunningTasksDock />
                  <ChatInputArea
                    ref={chatInputRef}
                    onSend={handleSendMessage}
                    onStop={stopAgent}
                    isAgentWorking={
                      status === "running" || status === "summarizing"
                    }
                    isSending={isSending}
                    isStopPending={false}
                    currentProject={currentProject}
                    activeThreadId={activeThreadId || undefined}
                    isGlobalMode={isGlobalMode}
                  />
                </>
              )}
          </div>
        </ResizablePanel>

        {!isCompactWindow && showContextPanel && (
          <>
            <ResizableHandle
              withHandle
              className="w-px bg-transparent data-[resize-handle-active]:bg-transparent after:bg-transparent hover:after:bg-muted/60 [&>div]:border-transparent [&>div]:bg-muted/50 [&>div]:opacity-0 [&>div]:transition-opacity hover:[&>div]:opacity-100 hover:[&>div]:bg-muted/70"
            />
            <ResizablePanel
              id="chat-context"
              order={3}
              defaultSize={20}
              minSize={15}
              maxSize={40}
              className="min-w-0 overflow-hidden"
            >
              <div
                data-tour="chat-context"
                className="h-full w-full min-w-0 overflow-hidden flex flex-col"
                style={{ contain: "content" }}
              >
                <ContextPanel
                  projectId={currentProject?.id}
                  activeThreadId={activeThreadId || ""}
                  autoSwitchToTab={undefined} // Disable auto-switch as we have Live Zone now
                  onClose={handleCloseContextPanel}
                  isGlobalMode={isGlobalMode}
                />
              </div>
            </ResizablePanel>
          </>
        )}
      </ResizablePanelGroup>

      {/* Compact Window Chat List Sheet */}
      {isCompactWindow && (
        <Sheet open={showChatListSheet} onOpenChange={setShowChatListSheet}>
          <SheetContent
            side="left"
            className="w-[320px] sm:w-[400px] max-w-[85vw] p-0 bg-background-soft [&>button]:hidden shadow-2xl flex flex-col min-w-0 overflow-hidden"
          >
            <SheetHeader className="sr-only">
              <SheetTitle>{t("chat.sidebar.tabChats")}</SheetTitle>
            </SheetHeader>
            <ChatSidebar
              threads={mappedThreads}
              activeThreadId={activeThreadId || ""}
              setActiveThreadId={(id) => {
                handleSetActiveThreadId(id)
                setShowChatListSheet(false)
              }}
              projectId={projectId}
              onDeleteThread={handleDeleteThread}
              onNewChat={() => {
                handleNewChat()
                setShowChatListSheet(false)
              }}
              onSelectDiff={handleSelectDiff}
              onQuoteFile={handleQuoteFile}
              activeTab={sidebarActiveTab}
              onTabChange={setSidebarActiveTab}
              expandAgentChanges={expandAgentChanges}
              fetchNextPage={fetchNextPage}
              hasNextPage={hasNextPage}
              isFetchingNextPage={isFetchingNextPage}
              onTogglePin={handleTogglePin}
            />
          </SheetContent>
        </Sheet>
      )}

      {/* Compact Window Context Sheet */}
      {isCompactWindow && (
        <Sheet open={showContextPanel} onOpenChange={setShowContextPanel}>
          <SheetContent
            side="right"
            className="w-[320px] sm:w-[400px] max-w-[85vw] p-0 bg-background-soft [&>button]:hidden shadow-2xl flex flex-col min-w-0 overflow-hidden"
          >
            <SheetHeader className="sr-only">
              <SheetTitle>{t("chat.context.title")}</SheetTitle>
            </SheetHeader>
            <ContextPanel
              projectId={currentProject?.id}
              activeThreadId={activeThreadId || ""}
              autoSwitchToTab={undefined}
              onClose={handleCloseContextPanel}
              isGlobalMode={isGlobalMode}
            />
          </SheetContent>
        </Sheet>
      )}

      {/* Memory Dialog removed: remember is now a one-click toggle on the message */}
      {/* Rewind Confirmation Dialog */}
      <RewindConfirmDialog
        open={isRewindDialogOpen}
        onOpenChange={setIsRewindDialogOpen}
        mode={confirmMode}
        onConfirm={(revertFiles) => {
          if (confirmMode === "rewind") {
            rewindMutation.mutate({
              revertFiles,
              messageId: selectedMessageId ?? undefined,
              content: _rewindContent,
            })
          } else {
            retryMutation.mutate({
              revertFiles,
              messageId: selectedMessageId ?? undefined,
            })
          }
        }}
      />
      {import.meta.env.DEV && <DebugManager />}
    </div>
  )
}
