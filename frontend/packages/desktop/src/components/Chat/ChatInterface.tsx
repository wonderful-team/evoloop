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
import { useCallback, useEffect, useMemo, useRef, useState } from "react"
import { useTranslation } from "react-i18next"
import { toast } from "sonner"
import { AgentService, ConversationsService, MemoryService } from "@/client"
import { isLoggedIn } from "@/hooks/useAuth"
import { useSystemEvent } from "@/hooks/useSystemEvent"
import { useAgentStore } from "@/stores/agentStore"
import { useChangesetStore } from "@/stores/changesetStore"
import { useChatStore } from "@/stores/chatStore"
import { useProjectStore } from "@/stores/projectStore"
import { useUIStore } from "@/stores/uiStore"
import { BreadcrumbStatus } from "./BreadcrumbStatus"
import { ChatInputArea, type ChatInputAreaHandle } from "./ChatInputArea"
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
import { TerminalCanvas } from "./TerminalCanvas"

export function ChatInterface() {
  // --- Store State (selective subscriptions to avoid unnecessary re-renders) ---
  const activeThreadId = useChatStore((s) => s.threadId)
  const storeProjectId = useChatStore((s) => s.projectId)
  const setThread = useChatStore((s) => s.setThread)
  const sendMessage = useChatStore((s) => s.sendMessage)
  const _truncateMessages = useChatStore((s) => s._truncateMessages)
  const isTerminalMode = useChatStore((s) => s.isTerminalMode)
  const _setTerminalMode = useChatStore((s) => s.setTerminalMode)
  const sendTerminalCommand = useChatStore((s) => s.sendTerminalCommand)
  const status = useAgentStore((s) => s.status)
  const humanRequest = useAgentStore((s) => s.humanRequest)
  const stopAgent = useAgentStore((s) => s.stopAgent)
  const markChangeAsViewed = useChangesetStore((s) => s.markChangeAsViewed)
  const markAllChangesAsViewed = useChangesetStore(
    (s) => s.markAllChangesAsViewed,
  )
  const _selectedModel = useChatStore((s) => s.selectedModel)

  const { t } = useTranslation()
  const currentProject = useProjectStore((s) => s.currentProject)
  const isGlobalMode = useProjectStore((s) => s.isGlobalMode)
  const queryClient = useQueryClient()

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
    setRewindContent,
    chatInputRef,
  })

  const [sidebarActiveTab, setSidebarActiveTab] = useState<string>("chats")
  const [expandAgentChanges, setExpandAgentChanges] = useState<boolean>(false)
  const [showChatListSheet, setShowChatListSheet] = useState(false)

  const projectId = currentProject?.id ?? storeProjectId ?? undefined

  // We maintain 'showContextPanel' locally as it involves UI preference
  // Global mode: hidden by default; Project mode: show by default
  // But respect user's manual preference stored in localStorage
  // In compact window (<1024px) it's a Sheet overlay, so keep it closed by default
  const [showContextPanel, setShowContextPanel] = useState(() => {
    const saved = localStorage.getItem("chat.contextPanel.hidden")
    if (saved === "true") return false
    if (typeof window !== "undefined" && window.innerWidth < 1024) return false
    return true
  })
  // Compact window detection (< 1024px, matching lg breakpoint of left sidebar)
  const [isCompactWindow, setIsCompactWindow] = useState(() => {
    if (typeof window !== "undefined") {
      return window.innerWidth < 1024
    }
    return false
  })

  useEffect(() => {
    const mql = window.matchMedia("(max-width: 1023px)")
    const handler = (e: MediaQueryListEvent) => {
      setIsCompactWindow(e.matches)
      // Closing the context sheet on shrink, otherwise it overlays the chat area
      if (e.matches) setShowContextPanel(false)
    }
    mql.addEventListener("change", handler)
    return () => mql.removeEventListener("change", handler)
  }, [])

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

  // Reset the manual close flag when agent finishes or starts a fresh run
  useEffect(() => {
    if (status !== "running") {
      hasManuallyClosedInCurrentRun.current = false
    }
  }, [status])

  // Auto-show context panel when agent starts working (skipped in compact window)
  useEffect(() => {
    if (
      !isCompactWindow &&
      status === "running" &&
      !showContextPanel &&
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
  }, [])

  // Persist manual open action
  const handleOpenContextPanel = useCallback(() => {
    localStorage.removeItem("chat.contextPanel.hidden")
    setShowContextPanel(true)
  }, [])

  const handleOpenChatList = useCallback(() => {
    setShowChatListSheet(true)
  }, [])

  // Refresh conversation list when a new conversation is created from
  // another device/channel (voice link, mobile, wecom, etc.)
  const handleConversationCreated = useCallback(() => {
    queryClient.invalidateQueries({ queryKey: ["projectConversations"] })
  }, [queryClient])

  useSystemEvent("conversation.created", handleConversationCreated)

  // --- Initialization ---
  useEffect(() => {
    // Get initial thread ID from URL if present, or create new
    const params = new URLSearchParams(window.location.search)
    const tid = params.get("thread_id")
    const initId = tid && tid.trim() !== "" ? tid : null

    // Check for message intent
    const pendingMessage = params.get("message")
    const shouldAutoSend = params.get("autoSend") === "true"
    const quoteId = params.get("quoteId")

    // Init Store - allow global mode (projectId can be 0)
    if (projectId !== undefined) {
      setThread(initId, projectId)
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
          window.history.replaceState(
            {},
            "",
            window.location.pathname + (tid ? `?thread_id=${tid}` : ""),
          )
        } else if (!shouldAutoSend && !quoteId) {
          // Just plain fill? (Need store support)
          window.history.replaceState(
            {},
            "",
            window.location.pathname + (tid ? `?thread_id=${tid}` : ""),
          )
        }
      }
    }
  }, [projectId, setThread, sendMessage]) // Run once when project loads

  // Handle Quote Deep Link - Dependent on Messages Loading
  useEffect(() => {
    const params = new URLSearchParams(window.location.search)
    const quoteId = params.get("quoteId")
    const pendingMessage = params.get("message")
    const _shouldAutoSend = params.get("autoSend") === "true"

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
          window.history.replaceState(
            {},
            "",
            window.location.pathname +
              window.location.search
                .replace(/quoteId=[^&]*&?/, "")
                .replace(/message=[^&]*&?/, "")
                .replace(/autoSend=[^&]*&?/, ""),
          )
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
      setThread(null, projectId)
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
      isRemembered,
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
    onError: (_err, { messageId, isRemembered }, context) => {
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
      if (projectId !== undefined) setThread(id, projectId)
    },
    [projectId, setThread],
  )

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
    if (status === "idle" || status === "interrupted") {
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
        <ResizablePanel
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
              onStopThread={handleStopThread}
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

        <ResizableHandle withHandle />

        {/* Center Chat Panel */}
        <ResizablePanel
          defaultSize={showContextPanel ? 64 : 84}
          minSize={20}
          className="min-w-0 overflow-hidden"
        >
          <div
            className="flex flex-col h-full relative min-h-0 min-w-0 w-full overflow-hidden"
            style={{ contain: "content" }}
          >
            {/* Breadcrumb Status */}
            <BreadcrumbStatus
              isCompactWindow={isCompactWindow}
              showContextPanel={showContextPanel}
              onOpenContextPanel={handleOpenContextPanel}
              onOpenChatList={handleOpenChatList}
            />
            <HITLBanner />
            <QuotaExhaustedBanner />

            <div
              className="flex-1 min-h-0 min-w-0 w-full"
              data-tour="chat-messages"
            >
              {isTerminalMode ? (
                <TerminalCanvas />
              ) : (
                <MessageList
                  onAddToMemory={handleAddToMemory}
                  onRewind={handleRewind}
                  onRetry={handleRetry}
                  onQuote={handleQuoteMessage}
                  onViewChangeset={handleViewChangeset}
                  footer={
                    <>
                      {status === "interrupted" && humanRequest && (
                        <HumanRequestCard request={humanRequest} />
                      )}
                      {status === "quota_exhausted" && <QuotaExhaustedCard />}
                    </>
                  }
                />
              )}
            </div>

            {/* Input Area */}
            {status !== "interrupted" && status !== "quota_exhausted" && (
              <ChatInputArea
                ref={chatInputRef}
                onSend={handleSendMessage}
                onStop={stopAgent}
                isAgentWorking={
                  status === "running" || status === "summarizing"
                }
                isSending={false}
                isStopPending={false}
                currentProject={currentProject}
                activeThreadId={activeThreadId || undefined}
                disabled={status === "interrupted"}
                isGlobalMode={isGlobalMode}
              />
            )}
          </div>
        </ResizablePanel>

        {!isCompactWindow && showContextPanel && (
          <>
            <ResizableHandle withHandle />
            <ResizablePanel
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
            className="w-[320px] sm:w-[400px] max-w-[85vw] p-0 border-r border-border bg-background [&>button]:hidden shadow-2xl flex flex-col min-w-0 overflow-hidden"
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
              onStopThread={handleStopThread}
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
            className="w-[320px] sm:w-[400px] max-w-[85vw] p-0 border-l border-border bg-background [&>button]:hidden shadow-2xl flex flex-col min-w-0 overflow-hidden"
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
              messageId: selectedMessageId,
              content: rewindContent,
            })
          } else {
            retryMutation.mutate({ revertFiles, messageId: selectedMessageId })
          }
        }}
      />
      {import.meta.env.DEV && <DebugManager />}
    </div>
  )
}
