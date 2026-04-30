import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { ArrowDown, Brain } from "lucide-react"
import { useCallback, useEffect, useRef, useState } from "react"
import { useTranslation } from "react-i18next"
import { toast } from "sonner"
import {
  AgentService,
  ConversationsService,
  MemoryService,
} from "@/client"
import { isLoggedIn } from "@/hooks/useAuth"

import {
  ResizableHandle,
  ResizablePanel,
  ResizablePanelGroup,
} from "@evoloop/shared/components/ui/resizable"
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
import { useProjectStore } from "@/stores/projectStore"
import { Button } from "@evoloop/shared/components/ui/button"
import { HITLBanner } from "./HITLBanner"
import { BreadcrumbStatus } from "./BreadcrumbStatus"
import { QuotaExhaustedBanner } from "./QuotaExhaustedBanner"
import { ChatInputArea, type ChatInputAreaHandle } from "./ChatInputArea"
import { MessageList } from "./MessageList"
import { ChatSidebar, type Thread } from "./ChatSidebar"
import { ContextPanel } from "./ContextPanel"

import { DiffDrawer } from "./DiffDrawer"
import { RewindConfirmDialog } from "./RewindConfirmDialog"

export function ChatInterface() {

  const { t } = useTranslation()
  const { currentProject, isGlobalMode } = useProjectStore()
  const projectId = currentProject?.id
  const queryClient = useQueryClient()

  // --- UI State ---
  const [selectedDiff, setSelectedDiff] = useState<{ path: string; diff: string } | null>(null)
  const [isDrawerOpen, setIsDrawerOpen] = useState(false)
  const [isRewindDialogOpen, setIsRewindDialogOpen] = useState(false)
  const [confirmMode, setConfirmMode] = useState<"rewind" | "retry">("rewind")
  const [selectedMessageId, setSelectedMessageId] = useState<string | undefined>(undefined)
  const [rewindContent, setRewindContent] = useState<string>("")
  const [sidebarActiveTab, setSidebarActiveTab] = useState<string>("chats")
  const [expandAgentChanges, setExpandAgentChanges] = useState<boolean>(false)

  // --- Store State ---
  // --- Store State (Granular Selectors to avoid full re-renders) ---
  const activeThreadId = useChatStore((s) => s.threadId)
  const messages = useChatStore((s) => s.messages)
  const status = useChatStore((s) => s.status)
  // Pagination state
  const hasMoreHistory = useChatStore((s) => s.hasMoreHistory)
  const isLoadingHistory = useChatStore((s) => s.isLoadingHistory)
  const loadMoreHistory = useChatStore((s) => s.loadMoreHistory)
  // Props required for components
  const setThread = useChatStore((s) => s.setThread)
  const sendMessage = useChatStore((s) => s.sendMessage)
  const stopAgent = useChatStore((s) => s.stopAgent)
  const _truncateMessages = useChatStore((s) => s._truncateMessages)
  const markAllChangesAsViewed = useChatStore((s) => s.markAllChangesAsViewed)
  const selectedModel = useChatStore((s) => s.selectedModel)

  // We maintain 'showContextPanel' locally as it involves UI preference
  // Global mode: hidden by default; Project mode: show by default
  // But respect user's manual preference stored in localStorage
  const [showContextPanel, setShowContextPanel] = useState(() => {
    const saved = localStorage.getItem("chat.contextPanel.hidden")
    // If user manually closed it before, respect that
    if (saved === "true") return false
    // Otherwise follow default logic
    return !isGlobalMode
  })
  const scrollRef = useRef<HTMLDivElement>(null)
  const chatInputRef = useRef<ChatInputAreaHandle | null>(null)

  // Smart Scroll State
  const [isUserScrolled, setIsUserScrolled] = useState(false)

  // Auto-show context panel when switching from global to project mode
  // But only if user hasn't manually closed it
  useEffect(() => {
    const saved = localStorage.getItem("chat.contextPanel.hidden")
    if (!isGlobalMode && currentProject && saved !== "true") {
      setShowContextPanel(true)
    }
  }, [isGlobalMode, currentProject])

  // Persist manual close action
  const handleCloseContextPanel = () => {
    localStorage.setItem("chat.contextPanel.hidden", "true")
    setShowContextPanel(false)
  }

  // Persist manual open action
  const handleOpenContextPanel = () => {
    localStorage.removeItem("chat.contextPanel.hidden")
    setShowContextPanel(true)
  }

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

    if (quoteId && messages.length > 0) {
      const msg = messages.find(m => m.id === quoteId || m.id.toString() === quoteId)
      if (msg) {
        // Pre-fill input if pending message exists
        if (pendingMessage) {
          chatInputRef.current?.setInput(pendingMessage + " ")
        }

        // Add reference (this appends)
        chatInputRef.current?.addReference({
          type: 'message',
          id: msg.id.toString(),
          name: msg.content.slice(0, 50) + (msg.content.length > 50 ? "..." : ""),
          detail: msg.role
        })

        // Handle Pending Message & AutoSend *AFTER* Quote is added
        if (pendingMessage) {
          if (shouldAutoSend) {
            // Optional: If we want to auto-send, we can trigger onSend here if we had access.
            // But since we are modifying internal state of InputArea, maybe just let user click send?
            // User requirement didn't explicitly demand auto-send for execute action with quote, 
            // but TodoList sets autoSend=true.
            // For now, let's just leave it filled for user review as adding context is "heavy".
          }
        }

        // Clear URL
        window.history.replaceState({}, '', window.location.pathname + (window.location.search.replace(/quoteId=[^&]*&?/, '').replace(/message=[^&]*&?/, '').replace(/autoSend=[^&]*&?/, '')))
      }
    }
  }, [messages]) // Re-run when messages load

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
  const { data: threadsData } = useQuery({
    queryKey: ["projectConversations", projectId],
    queryFn: async () =>
      ConversationsService.listConversations({ projectId: projectId! }),
    enabled: projectId !== undefined,
  })

  const threads: Thread[] = (Array.isArray(threadsData) ? threadsData : []).map(
    (t: any) => ({
      thread_id: t.thread_id,
      title: t.title,
      updated_at: t.updated_at || new Date().toISOString(),
      status: t.status,
    }),
  )

  // --- Handlers ---

  const handleNewChat = useCallback(() => {
    if (projectId !== undefined) {
      setThread(null, projectId)
    }
  }, [projectId, setThread])

  // Wrapper for sendMessage to handle post-send actions
  const handleSendMessage = async (content: string, attachments?: any[]) => {
    const isNewThread = messages.length === 0
    await sendMessage(content, attachments)
    // If this was a new thread (first message), refresh the conversation list
    if (isNewThread && projectId !== undefined) {
      queryClient.invalidateQueries({ queryKey: ["projectConversations", projectId] })
    }
  }

  const handleDeleteThread = async (id: string) => {
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
  }

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
      if (!projectId) throw new Error("No project")
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

  const rewindMutation = useMutation({
    // @ts-ignore
    mutationFn: ({ revertFiles, messageId }: { revertFiles: boolean; messageId?: string }) =>
      // @ts-ignore
      ConversationsService.rewindConversation({
        threadId: activeThreadId!,
        requestBody: {
          revert_files: revertFiles,
          message_id: messageId
        }
      } as any),
    onSuccess: (data: any) => {
      // Reload store
      if (activeThreadId && projectId) setThread(activeThreadId, projectId)
      const filesMsg = data.files_reverted && data.files_reverted > 0
        ? ` (${t("chat.interface.filesReverted", { count: data.files_reverted })})`
        : ""

      // If we are rewinding a human message, refill the input
      if (rewindContent) {
        chatInputRef.current?.setInput(rewindContent)
        setRewindContent("")
      }

      toast.success(`${t("chat.interface.rewindSuccess")}${filesMsg}`)
      setIsRewindDialogOpen(false)
    },
  })

  // Retry Logic
  const retryMutation = useMutation({
    mutationFn: async ({ revertFiles, messageId }: { revertFiles: boolean; messageId?: string }) => {
      // @ts-ignore
      return AgentService.retryChat({
        requestBody: {
          thread_id: activeThreadId,
          message: "", // Backend finds the target user message
          project_id: projectId,
          revert_files: revertFiles,
          message_id: messageId ? parseInt(messageId) : undefined,
          model: selectedModel,
        }
      } as any)
    },
    onMutate: () => {
      // Optimistically truncate the messages list to remove old AI messages
      const lastHumanIndex = [...messages].reverse().findIndex(m => m.role === "human")
      if (lastHumanIndex !== -1) {
        const actualIndex = messages.length - 1 - lastHumanIndex
        _truncateMessages(actualIndex + 1)
      }
    },
    // @ts-ignore
    onSuccess: (data: any) => {
      const filesMsg = data.files_reverted && data.files_reverted > 0
        ? ` (${t("chat.interface.filesReverted", { count: data.files_reverted })})`
        : ""
      toast.success(`${t("chat.interface.retrying")}${filesMsg}`)
      // Reload store to reflect rolled back state and new streaming status
      if (activeThreadId && projectId) setThread(activeThreadId, projectId)
      setIsRewindDialogOpen(false)
    },
    onError: () => {
      toast.error(t("chat.interface.retryFailed"))
    }
  })

  const handleQuoteMessage = (msg: any) => {
    // Construct reference item
    // Used for quoting/referencing a historical message
    chatInputRef.current?.addReference({
      type: 'message',
      id: msg.id.toString(), // Message ID or Thread ID? Usually ID for direct quote.
      // Actually for message reference we might want the thread ID if we want to search ctx?
      // But here we are referencing a specific message content.
      // The ReferencePicker used thread_id for search results because searchConversations returns threads/snippets.
      // The backend MessageReference stores target_id.
      // Let's use message ID.
      name: msg.content.slice(0, 50) + (msg.content.length > 50 ? "..." : ""),
      detail: msg.role
    })
  }

  const handleQuoteFile = (file: any) => {
    chatInputRef.current?.addReference({
      type: 'file',
      id: file.path,
      name: file.name,
      detail: file.path
    })
  }

  // Handle view changeset from message inline hint
  const handleViewChangeset = () => {
    // Switch to files tab
    setSidebarActiveTab("files")
    // Expand Agent Changes panel
    setExpandAgentChanges(true)
    // Mark all as viewed
    markAllChangesAsViewed()
  }

  // --- Auto Scroll Logic ---
  // Auto-scroll logic

  // Handle User Scroll Interaction
  const handleScroll = useCallback(() => {
    if (!scrollRef.current) return
    const { scrollTop, scrollHeight, clientHeight } = scrollRef.current
    // If user is not at the bottom (threshold 50px), mark as user scrolled
    const isAtBottom = scrollHeight - scrollTop - clientHeight < 100
    setIsUserScrolled(!isAtBottom)

    // Trigger load more history when near top
    if (scrollTop < 100 && hasMoreHistory && !isLoadingHistory) {
      console.log('[ChatInterface] Near top, triggering loadMoreHistory')
      loadMoreHistory()
    }
  }, [hasMoreHistory, isLoadingHistory, loadMoreHistory])

  const scrollToBottom = useCallback((smooth = false) => {
    scrollRef.current?.scrollTo({
      top: scrollRef.current.scrollHeight,
      behavior: smooth ? "smooth" : "auto",
    })
  }, [])

  useEffect(() => {
    // Only auto-scroll if user hasn't scrolled up
    if (!isUserScrolled) {
      scrollToBottom()
    }
  }, [isUserScrolled, scrollToBottom, messages]) // Trigger on content updates

  useEffect(() => {
    setIsUserScrolled(false)
    scrollToBottom()
  }, [scrollToBottom])

  // Deep Linking Listener
  useEffect(() => {
    const handleScrollToRun = (e: CustomEvent<{ runId: string }>) => {
      const runId = e.detail.runId
      // Find DOM element within scroll container
      const el = scrollRef.current?.querySelector(`[data-run-id= "${runId}"]`)
      if (el) {
        el.scrollIntoView({ behavior: "smooth", block: "start" })
        // Visual indicator
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
    <div className="flex flex-col h-full relative bg-background overflow-hidden">
      <ResizablePanelGroup direction="horizontal" className="h-full w-full">
        {/* Left Sidebar Panel */}
        <ResizablePanel
          defaultSize={20}
          minSize={15}
          maxSize={40}
          className="hidden lg:block min-w-[200px]"
        >
          <ChatSidebar
            threads={threads.map(t => ({
              ...t,
              // Override status if it's the active thread, using reliable store state
              status: t.thread_id === activeThreadId ? status : t.status
            }))}
            activeThreadId={activeThreadId || ""}
            setActiveThreadId={(id) => projectId !== undefined && setThread(id, projectId)}
            projectId={projectId}
            onDeleteThread={handleDeleteThread}
            onStopThread={handleStopThread}
            onNewChat={handleNewChat}
            onSelectDiff={(path, diff) => {
              setSelectedDiff({ path, diff })
              setIsDrawerOpen(true)
            }}
            onQuoteFile={handleQuoteFile}
            activeTab={sidebarActiveTab}
            onTabChange={setSidebarActiveTab}
            expandAgentChanges={expandAgentChanges}
          />
        </ResizablePanel>

        <ResizableHandle withHandle />

        {/* Center Chat Panel */}
        <ResizablePanel defaultSize={showContextPanel ? 60 : 80} minSize={20} className="min-w-0">
          <div className="flex flex-col h-full relative min-h-0 min-w-0">
            {/* Top Right Controls */}
            <div className="absolute top-4 right-4 z-20 flex items-center gap-2">
              {/* Toggle Context Panel Button */}
              {!showContextPanel && (
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

            <div
              className="flex-1 overflow-y-auto min-h-0 min-w-0 scroll-smooth"
              ref={scrollRef}
              onScroll={handleScroll}
              data-tour="chat-messages"
            >
              <div className="space-y-6 px-4 sm:px-6 lg:px-8 pb-1 pt-4 min-w-0">
                <MessageList
                  messages={messages}
                  hasMoreHistory={hasMoreHistory}
                  isLoadingHistory={isLoadingHistory}
                  onAddToMemory={(txt) => {
                    setMemoryContent(txt)
                    setIsMemoryDialogOpen(true)
                  }}
                  onRewind={(msg) => {
                    // Check if any message from this point forward has file operations
                    const index = messages.findIndex(m => m.id === msg.id)
                    const subMessages = messages.slice(index)
                    const hasFiles = subMessages.some(m => m.has_file_operations)

                    setSelectedMessageId(msg.id.toString())

                    // Capure content if it's a human message to refill later
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
                  }}
                  onRetry={(msg) => {
                    // Targeted Retry starting from the specific user message
                    const index = messages.findIndex(m => m.id === msg.id)
                    const subMessages = messages.slice(index + 1)

                    const hasFiles = subMessages.some(m => m.has_file_operations)

                    setSelectedMessageId(msg.id.toString())
                    if (hasFiles) {
                      setConfirmMode("retry")
                      setIsRewindDialogOpen(true)
                    } else {
                      retryMutation.mutate({ revertFiles: false, messageId: msg.id.toString() })
                    }
                  }}
                  onQuote={(msg) => handleQuoteMessage(msg)}
                  onViewChangeset={handleViewChangeset}
                />
              </div>
            </div>

            {/* Scroll to Bottom Button */}
            {isUserScrolled && (
              <div className="absolute bottom-4 right-4 z-10 animate-in fade-in slide-in-from-bottom-2">
                <Button
                  size="icon"
                  variant="secondary"
                  className="rounded-full shadow-md bg-background/80 backdrop-blur border"
                  onClick={() => scrollToBottom()}
                >
                  <ArrowDown className="h-4 w-4" />
                </Button>
              </div>
            )}

            {/* HumanRequestCard moved to AgentCanvas */}

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

        {showContextPanel && (
          <>
            <ResizableHandle withHandle />
            <ResizablePanel
              defaultSize={20}
              minSize={15}
              maxSize={40}
              className="min-w-[200px]"
            >
              <div data-tour="chat-context" className="h-full">
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
                onChange={(e) => setMemoryName(e.target.value)}
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
      {/* Diff Drawer */}
      <DiffDrawer
        isOpen={isDrawerOpen}
        onClose={() => setIsDrawerOpen(false)}
        path={selectedDiff?.path || null}
        diff={selectedDiff?.diff || null}
      />
    </div>
  )
}
