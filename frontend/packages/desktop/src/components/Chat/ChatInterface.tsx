import { useMutation, useQueryClient, useInfiniteQuery } from "@tanstack/react-query"
import { Brain } from "lucide-react"
import { useCallback, useEffect, useRef, useState, useMemo } from "react"
import { useTranslation } from "react-i18next"
import { toast } from "sonner"
import {
  AgentService,
  ConversationsService,
  MemoryService,
} from "@/client"
import { ChatConnection } from "@/lib/ChatConnection"
import { isLoggedIn } from "@/hooks/useAuth"

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
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogFooter,
} from "@evoloop/shared/components/ui/dialog"
import { Input } from "@evoloop/shared/components/ui/input"
import { Label } from "@evoloop/shared/components/ui/label"
import { useChatStore } from "@/stores/chatStore"
import { useUIStore } from "@/stores/uiStore"
import { useProjectStore } from "@/stores/projectStore"
import { Button } from "@evoloop/shared/components/ui/button"
import { HITLBanner } from "./HITLBanner"
import { BreadcrumbStatus } from "./BreadcrumbStatus"
import { QuotaExhaustedBanner } from "./QuotaExhaustedBanner"
import { ChatInputArea, type ChatInputAreaHandle } from "./ChatInputArea"
import { MessageList } from "./MessageList"
import { ChatSidebar, type Thread } from "./ChatSidebar"
import { ContextPanel } from "./ContextPanel"
import { RewindConfirmDialog } from "./RewindConfirmDialog"
import { DebugManager } from "./DebugManager"
import { HumanRequestCard } from "./HumanRequestCard"
import { QuotaExhaustedCard } from "./QuotaExhaustedCard"
import { useAgentStore } from "@/stores/agentStore"
import { useChangesetStore } from "@/stores/changesetStore"
import { useChatMutations } from "./hooks/useChatMutations"

export function ChatInterface() {
  // --- Store State (selective subscriptions to avoid unnecessary re-renders) ---
  const activeThreadId = useChatStore(s => s.threadId)
  const storeProjectId = useChatStore(s => s.projectId)
  const setThread = useChatStore(s => s.setThread)
  const sendMessage = useChatStore(s => s.sendMessage)
  const _truncateMessages = useChatStore(s => s._truncateMessages)
  const status = useAgentStore(s => s.status)
  const humanRequest = useAgentStore(s => s.humanRequest)
  const stopAgent = useAgentStore(s => s.stopAgent)
  const markChangeAsViewed = useChangesetStore(s => s.markChangeAsViewed)
  const markAllChangesAsViewed = useChangesetStore(s => s.markAllChangesAsViewed)
  const selectedModel = useChatStore(s => s.selectedModel)

  const { t } = useTranslation()
  const currentProject = useProjectStore(s => s.currentProject)
  const isGlobalMode = useProjectStore(s => s.isGlobalMode)
  const queryClient = useQueryClient()

  // --- UI State ---
  const [isRewindDialogOpen, setIsRewindDialogOpen] = useState(false)
  const [rewindTargetId, setRewindTargetId] = useState<string | null>(null)
  const [rewindRevertFiles, setRewindRevertFiles] = useState(true)
  const [rewindContent, setRewindContent] = useState("")
  const [confirmMode, setConfirmMode] = useState<"rewind" | "retry">("rewind")
  const [selectedMessageId, setSelectedMessageId] = useState<string | null>(null)
  
  const chatInputRef = useRef<ChatInputAreaHandle | null>(null)

  // Custom Hook for Mutations
  const { rewindMutation, retryMutation } = useChatMutations({
    setIsRewindDialogOpen,
    setRewindContent,
    chatInputRef
  })

  const [sidebarActiveTab, setSidebarActiveTab] = useState<string>("chats")
  const [expandAgentChanges, setExpandAgentChanges] = useState<boolean>(false)

  const projectId = (currentProject?.id ?? storeProjectId) ?? undefined

  // We maintain 'showContextPanel' locally as it involves UI preference
  // Global mode: hidden by default; Project mode: show by default
  // But respect user's manual preference stored in localStorage
  const [showContextPanel, setShowContextPanel] = useState(() => {
    const saved = localStorage.getItem("chat.contextPanel.hidden")
    if (saved === "true") return false
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
    const handler = (e: MediaQueryListEvent) => setIsCompactWindow(e.matches)
    mql.addEventListener("change", handler)
    return () => mql.removeEventListener("change", handler)
  }, [])

  // Auto-show context panel when switching from global to project mode
  // But only if user hasn't manually closed it
  useEffect(() => {
    const saved = localStorage.getItem("chat.contextPanel.hidden")
    if (!isGlobalMode && currentProject && saved !== "true") {
      setShowContextPanel(true)
    }
  }, [isGlobalMode, currentProject])

  // Track if user manually closed context panel during the CURRENT run
  const hasManuallyClosedInCurrentRun = useRef(false)

  // Reset the manual close flag when agent finishes or starts a fresh run
  useEffect(() => {
    if (status !== "running") {
      hasManuallyClosedInCurrentRun.current = false
    }
  }, [status])

  // Auto-show context panel when agent starts working
  useEffect(() => {
    if (status === "running" && !showContextPanel && !hasManuallyClosedInCurrentRun.current) {
      setShowContextPanel(true)
    }
  }, [status, showContextPanel])

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
          window.history.replaceState({}, '', window.location.pathname + (tid ? `?thread_id=${tid}` : ''))
        } else if (!shouldAutoSend && !quoteId) {
          // Just plain fill? (Need store support)
          window.history.replaceState({}, '', window.location.pathname + (tid ? `?thread_id=${tid}` : ''))
        }
      }
    }
  }, [projectId, setThread, sendMessage]) // Run once when project loads

  // Handle Quote Deep Link - Dependent on Messages Loading
  useEffect(() => {
    const params = new URLSearchParams(window.location.search)
    const quoteId = params.get("quoteId")
    const pendingMessage = params.get("message")
    const shouldAutoSend = params.get("autoSend") === "true"

    if (!quoteId) return

    const checkAndHandleQuote = (currentMessages: any[]) => {
      if (currentMessages.length > 0) {
        const msg = currentMessages.find(m => m.id === quoteId || m.id.toString() === quoteId)
        if (msg) {
          // Pre-fill input if pending message exists
          if (pendingMessage) {
            chatInputRef.current?.setInput(pendingMessage + " ")
          }

          // Add reference
          chatInputRef.current?.addReference({
            type: 'message',
            id: msg.id.toString(),
            name: msg.content.slice(0, 50) + (msg.content.length > 50 ? "..." : ""),
            detail: msg.role
          })

          // Clear URL
          window.history.replaceState({}, '', window.location.pathname + (window.location.search.replace(/quoteId=[^&]*&?/, '').replace(/message=[^&]*&?/, '').replace(/autoSend=[^&]*&?/, '')))
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
      ConversationsService.listConversations({ projectId: projectId! }).catch(() => {
        // Error will be handled by main.tsx's handleApiError
      })
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
    return threads.map(t => ({
      ...t,
      // Override status if it's the active thread, using reliable store state
      status: t.thread_id === activeThreadId ? status : t.status
    }))
  }, [threads, activeThreadId, status])

  const handleTogglePin = useCallback(async (id: string, isPinned: boolean) => {
    try {
      await ConversationsService.updateConversation({
        threadId: id,
        requestBody: { is_pinned: isPinned },
      })
      queryClient.invalidateQueries({ queryKey: ["projectConversations", projectId] })
      toast.success(isPinned ? "已置顶会话" : "已取消置顶")
    } catch (err) {
      console.error(err)
      toast.error("操作失败")
    }
  }, [projectId, queryClient])

  // --- Handlers ---

  const handleNewChat = useCallback(() => {
    if (projectId !== undefined) {
      setThread(null, projectId)
    }
  }, [projectId, setThread])

  // Wrapper for sendMessage to handle post-send actions
  const handleSendMessage = useCallback(async (content: string, pickedFiles?: any[]) => {
    const isNewThread = useChatStore.getState().messages.length === 0
    
    const sendPromise = sendMessage(content, pickedFiles)

    // 立即触发滚动到底部，不需要等待 AI 响应完成
    // 发送消息后强制滚到底部
    window.dispatchEvent(new CustomEvent('chat-scroll-to-bottom'))

    await sendPromise

    // If this was a new thread (first message), refresh the conversation list
    if (isNewThread && projectId !== undefined) {
      queryClient.invalidateQueries({ queryKey: ["projectConversations", projectId] })
    }
  }, [sendMessage, projectId, queryClient])

  const handleDeleteThread = useCallback(async (id: string) => {
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
  }, [activeThreadId, threads, projectId, setThread, handleNewChat, queryClient, t])

  const handleStopThread = useCallback(async (id: string) => {
    // If stopping active, use store action. Else API.
    if (id === activeThreadId) {
      await stopAgent()
    } else {
      await AgentService.stopChat({
        requestBody: { thread_id: id, message: "" },
      })
      toast.info(t("chat.interface.stopAgentSuccess"))
    }
  }, [activeThreadId, stopAgent, t])

  // --- Side Effect Mutations (Keep here or move to store if generic) ---
  // These are specific to message item actions

  // Memory Dialog State
  const [isMemoryDialogOpen, setIsMemoryDialogOpen] = useState(false)
  const [memoryContent, setMemoryContent] = useState("")
  const [memoryName, setMemoryName] = useState("")

  const addToMemoryMutation = useMutation({
    mutationFn: async ({ text, name }: { text: string; name: string }) => {
      if (projectId === undefined || projectId === null) throw new Error("No project")
      return MemoryService.addConcept({
        projectId,
        requestBody: {
          name: name || t("chat.interface.learnedFromChat"),
          description: text,
          related_files: [],
        },
      })
    },
    onSuccess: () => {
      toast.success(t("chat.interface.addMemorySuccess"))
      queryClient.invalidateQueries({ queryKey: ["projectMemory"] })
      setIsMemoryDialogOpen(false)
      setMemoryName("")
    },
  })


  const handleQuoteMessage = useCallback((msg: any) => {
    if (!msg || !msg.id) return
    const quoteText = msg.effective_content !== undefined && msg.effective_content.trim() !== "" ? msg.effective_content : msg.content;
    
    // Construct reference item
    chatInputRef.current?.addReference({
      type: 'message',
      id: msg.id.toString(),
      name: quoteText.slice(0, 50) + (quoteText.length > 50 ? "..." : ""),
      detail: msg.role
    })
  }, [])

  const handleQuoteFile = useCallback((file: any) => {
    chatInputRef.current?.addReference({
      type: 'file',
      id: file.path,
      name: file.name,
      detail: file.path
    })
  }, [])

  // Handle view changeset from message snapshot
  const handleViewChangeset = useCallback((_messageId?: string | number, path?: string, diff?: string) => {
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
          const file = useChangesetStore.getState().changeset.find(f => f.path === path)
          if (file) {
            useUIStore.getState().setPreviewDiff({ path: file.path, diff: file.diff || "" })
          }
        }
        // Mark as viewed
        markChangeAsViewed(path, threadId)
      } else {
        // Mark all as viewed
        markAllChangesAsViewed(threadId)
      }
    }
  }, [markChangeAsViewed, markAllChangesAsViewed, activeThreadId])

  const handleSetActiveThreadId = useCallback((id: string) => {
    if (projectId !== undefined) setThread(id, projectId)
  }, [projectId, setThread])

  const handleSelectDiff = useCallback((path: string, diff: string) => {
    useUIStore.getState().setPreviewDiff({ path, diff })
  }, [])

  const handleAddToMemory = useCallback((txt: string) => {
    setMemoryContent(txt)
    setIsMemoryDialogOpen(true)
  }, [])

  const handleRewind = useCallback((msg: any) => {
    const currentMessages = useChatStore.getState().messages
    const index = currentMessages.findIndex(m => m.id === msg.id)
    const subMessages = currentMessages.slice(index)
    const hasFiles = subMessages.some(m => m.has_file_operations)

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
      rewindMutation.mutate({ revertFiles: false, messageId: msg.id.toString() })
    }
  }, [rewindMutation])

  const handleRetry = useCallback((msg: any) => {
    const currentMessages = useChatStore.getState().messages
    const index = currentMessages.findIndex(m => m.id === msg.id)
    const subMessages = currentMessages.slice(index + 1)
    const hasFiles = subMessages.some(m => m.has_file_operations)

    setSelectedMessageId(msg.id.toString())
    if (hasFiles) {
      setConfirmMode("retry")
      setIsRewindDialogOpen(true)
    } else {
      retryMutation.mutate({ revertFiles: false, messageId: msg.id.toString() })
    }
  }, [retryMutation])

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
        setTimeout(() => el.classList.remove("ring-2", "ring-primary/20", "rounded-lg"), 2000)
      } else {
        toast.info(t("chat.interface.messageNotLoaded"))
      }
    }

    window.addEventListener("chat-scroll-to-run" as any, handleScrollToRun as any)
    return () => {
      window.removeEventListener("chat-scroll-to-run" as any, handleScrollToRun as any)
    }
  }, [])

  // Keyboard Shortcuts: Esc to Stop Agent
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      // Only trigger if Agent is working and Esc is pressed
      if (e.key === "Escape" && (status === "running" || status === "summarizing")) {
        console.log("[ChatInterface] Esc pressed, stopping agent.")
        handleStopThread(activeThreadId || "")
      }
    }

    window.addEventListener("keydown", handleKeyDown)
    return () => window.removeEventListener("keydown", handleKeyDown)
  }, [status, activeThreadId, handleStopThread])

  return (
    <div className="flex flex-col h-full w-full min-w-0 relative bg-background overflow-hidden">
      <ResizablePanelGroup direction="horizontal" className="h-full w-full min-w-0 overflow-hidden">
        {/* Left Sidebar Panel */}
        <ResizablePanel
          defaultSize={16}
          minSize={15}
          maxSize={40}
          className="hidden lg:block min-w-[100px] overflow-hidden"
        >
          <div style={{ contain: 'content', height: '100%', width: '100%', minWidth: 0 }}>
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
        <ResizablePanel defaultSize={showContextPanel ? 64 : 84} minSize={20} className="min-w-0 overflow-hidden">
          <div className="flex flex-col h-full relative min-h-0 min-w-0 w-full overflow-hidden" style={{ contain: 'content' }}>
            {/* Top Right Controls */}
            <div className="absolute top-4 right-4 z-20 flex items-center gap-2">
              {/* Toggle Context Panel Button */}
              {(!showContextPanel || isCompactWindow) && (
                <Button
                  variant="ghost"
                  size="icon"
                  onClick={handleOpenContextPanel}
                  title={t("common.openContextPanel")}
                >
                  <Brain className="h-5 w-5 text-muted-foreground" />
                </Button>
              )}
            </div>

            {/* Breadcrumb Status */}
            <BreadcrumbStatus />
            <HITLBanner />
            <QuotaExhaustedBanner />

            <div className="flex-1 min-h-0 min-w-0 w-full" data-tour="chat-messages">
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
                    {status === "quota_exhausted" && (
                      <QuotaExhaustedCard />
                    )}
                  </>
                }
              />
            </div>

            {/* Input Area */}
            <ChatInputArea
              ref={chatInputRef}
              onSend={handleSendMessage}
              onStop={stopAgent}
              isAgentWorking={status === "running" || status === "summarizing"}
              isSending={false}
              isStopPending={false}
              currentProject={currentProject}
              activeThreadId={activeThreadId || undefined}
              disabled={status === "interrupted"}
              isGlobalMode={isGlobalMode}
            />
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
              <div data-tour="chat-context" className="h-full w-full min-w-0 overflow-hidden flex flex-col" style={{ contain: 'content' }}>
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

      {/* Compact Window Context Sheet */}
      {isCompactWindow && (
        <Sheet open={showContextPanel} onOpenChange={setShowContextPanel}>
          <SheetContent side="right" className="w-[320px] sm:w-[400px] max-w-[85vw] p-0 border-l border-border bg-background [&>button]:hidden shadow-2xl flex flex-col min-w-0 overflow-hidden">
            <SheetHeader className="sr-only">
              <SheetTitle>{t("chat.context.title", { defaultValue: "Agent 工作台" })}</SheetTitle>
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

      {/* Memory Dialog */}
      <Dialog open={isMemoryDialogOpen} onOpenChange={setIsMemoryDialogOpen}>
        <DialogContent className="sm:max-w-[425px]">
          <DialogHeader>
            <DialogTitle>{t("chat.interface.memorizeConfirm")}</DialogTitle>
          </DialogHeader>
          <div className="grid gap-4 py-4">
            <div className="grid grid-cols-4 items-center gap-4">
              <Label htmlFor="name" className="text-right">
                {t("chat.interface.conceptName")}
              </Label>
              <Input
                id="name"
                value={memoryName}
                onChange={(e: React.ChangeEvent<HTMLInputElement>) => setMemoryName(e.target.value)}
                placeholder={t("chat.interface.conceptPlaceholder")}
                className="col-span-3"
                autoFocus
              />
            </div>
            <div className="grid grid-cols-4 items-center gap-4">
              <Label className="text-right">{t("chat.interface.contentLabel")}</Label>
              <div className="col-span-3 text-xs text-muted-foreground line-clamp-3 bg-muted p-2 rounded">
                {memoryContent}
              </div>
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setIsMemoryDialogOpen(false)}>
              {t("chat.interface.cancel")}
            </Button>
            <Button onClick={() => addToMemoryMutation.mutate({ text: memoryContent, name: memoryName })}>
              {t("chat.interface.save")}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
      {/* Rewind Confirmation Dialog */}
      <RewindConfirmDialog
        open={isRewindDialogOpen}
        onOpenChange={setIsRewindDialogOpen}
        mode={confirmMode}
        onConfirm={(revertFiles) => {
          if (confirmMode === "rewind") {
            rewindMutation.mutate({ revertFiles, messageId: selectedMessageId })
          } else {
            retryMutation.mutate({ revertFiles, messageId: selectedMessageId })
          }
        }}
      />
      {import.meta.env.DEV && <DebugManager />}
    </div>
  )
}
