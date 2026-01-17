import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { ArrowDown, Bot, Brain, ChevronDown, Loader2 } from "lucide-react"
import { memo, useCallback, useEffect, useRef, useState } from "react"
import { useTranslation } from "react-i18next"
import { toast } from "sonner"
import {
  AgentService,
  ConversationsService,
  FilesService,
  MemoryService,
} from "@/client"
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from "@/components/ui/collapsible"

import {
  ResizableHandle,
  ResizablePanel,
  ResizablePanelGroup,
} from "@/components/ui/resizable"
import { useChatStore } from "@/stores/chatStore"
import { useProjectStore } from "@/stores/projectStore"
import { Avatar, AvatarFallback, AvatarImage } from "../ui/avatar"
import { Button } from "../ui/button"
import { ArtifactsList } from "./Artifacts/ArtifactsList"
import { ChatInputArea, type ChatInputAreaHandle } from "./ChatInputArea"
import { ChatMessageItem } from "./ChatMessageItem"
import { ChatSidebar, type Thread } from "./ChatSidebar"
import { ContextPanel } from "./ContextPanel"
import { MessageContent } from "./MessageContent"
import { TaskSteps } from "./TaskSteps"

import { HITLBanner } from "./HITLBanner"

const CompositeAIBubble = memo(() => {
  const streamedContent = useChatStore((s) => s.streamedContent)
  const tasks = useChatStore((s) => s.tasks)
  const artifacts = useChatStore((s) => s.artifacts)
  const status = useChatStore((s) => s.status)

  // Only show when there's activity (streaming content, running tasks, or artifacts)
  const hasContent =
    streamedContent || tasks.some((t) => t.status === "running") || artifacts.length > 0
  if (!hasContent && status === "idle") return null

  return (
    <div className="flex gap-3 justify-start items-start mb-4">
      <Avatar className="h-8 w-8 mt-1 shrink-0">
        <AvatarImage src="/bot-avatar.png" />
        <AvatarFallback>
          <Bot size={16} />
        </AvatarFallback>
      </Avatar>
      <div className="flex-1 max-w-[80%]">
        {/* Collapsible Task Steps - Embedded within message bubble context */}
        {tasks.length > 0 && (
          <Collapsible defaultOpen={true} className="mb-2">
            <CollapsibleTrigger asChild>
              <Button
                variant="ghost"
                size="sm"
                className="h-6 p-0 text-muted-foreground hover:bg-transparent flex items-center gap-1 text-xs"
              >
                <Loader2
                  size={12}
                  className={status === "running" ? "animate-spin" : ""}
                />
                <span className="italic">
                  {tasks.filter((t) => t.status === "done").length}/
                  {tasks.length} steps
                </span>
                <ChevronDown size={12} className="opacity-50" />
              </Button>
            </CollapsibleTrigger>
            <CollapsibleContent className="mt-1">
              <TaskSteps tasks={tasks} />
            </CollapsibleContent>
          </Collapsible>
        )}

        {/* Artifacts List */}
        {artifacts.length > 0 && <ArtifactsList artifacts={artifacts} />}

        {/* Streaming Content */}
        {streamedContent && (
          <div className="rounded-lg px-4 py-3 bg-muted text-foreground text-sm leading-relaxed shadow-sm overflow-hidden">
            <MessageContent content={streamedContent} />
          </div>
        )}

        {/* Blinking Cursor (when running but no content yet) */}
        {!streamedContent && status === "running" && (
          <div className="rounded-lg px-4 py-3 bg-muted text-foreground text-sm leading-relaxed shadow-sm">
            <span className="inline-block w-1.5 h-4 bg-primary align-middle animate-pulse" />
          </div>
        )}
      </div>
    </div>
  )
})
CompositeAIBubble.displayName = "CompositeAIBubble"

const StatusIndicator = memo(() => {
  const { t } = useTranslation()
  const status = useChatStore((s) => s.status)
  const tasks = useChatStore((s) => s.tasks)
  const agentState = useChatStore((s) => s.agentState)

  if (status !== "running" && status !== "SUMMARIZING") return null

  // Find active task name (fallback if no high-level state)
  const runningTask = tasks.find((t: any) => t.status === "running")
  // Prefer Agent State (High Level) > Running Task (Low Level) > Default
  const displayTask = agentState?.task_name || runningTask?.name || t("chat.status.working")
  // Translate mode: agentState.mode is usually uppercase e.g. "PLANNING"
  const rawMode = agentState?.mode
  const displayMode = rawMode
    ? t(`chat.modes.${rawMode.replace(" ", "_")}`, rawMode) // Fallback to rawMode if key missing
    : t("chat.status.busy")

  const getModeColor = (mode: string) => {
    switch (mode.toUpperCase()) {
      case 'PLANNING': return 'text-purple-600 bg-purple-100/50 dark:bg-purple-900/20'
      case 'RESEARCHING':
      case 'DEEP RESEARCH': return 'text-blue-600 bg-blue-100/50 dark:bg-blue-900/20'
      case 'CODING': return 'text-amber-600 bg-amber-100/50 dark:bg-amber-900/20'
      case 'REVIEWING': return 'text-pink-600 bg-pink-100/50 dark:bg-pink-900/20'
      default: return 'text-muted-foreground bg-muted'
    }
  }

  return (
    <div className="flex items-center gap-3 pl-11 mb-4 animate-in fade-in duration-300">
      <div className="relative">
        <Loader2 size={16} className="animate-spin text-primary" />
      </div>

      <div className="flex items-center gap-2 overflow-hidden">
        {agentState && (
          <span className={`text-[10px] font-bold px-1.5 py-0.5 rounded uppercase tracking-wider ${getModeColor(displayMode)}`}>
            {displayMode}
          </span>
        )}
        <span className="text-sm text-muted-foreground truncate animate-pulse selection:bg-transparent">
          {displayTask}
        </span>
      </div>
    </div>
  )
})
StatusIndicator.displayName = "StatusIndicator"

export function ChatInterface() {
  const { t } = useTranslation()
  const { currentProject } = useProjectStore()
  const projectId = currentProject?.id
  const queryClient = useQueryClient()

  // --- Store State ---
  // --- Store State (Granular Selectors to avoid full re-renders) ---
  const activeThreadId = useChatStore((s) => s.threadId)
  const messages = useChatStore((s) => s.messages)
  const status = useChatStore((s) => s.status)
  const tasks = useChatStore((s) => s.tasks)
  const streamedContent = useChatStore((s) => s.streamedContent)
  const setThread = useChatStore((s) => s.setThread)
  const sendMessage = useChatStore((s) => s.sendMessage)
  const stopAgent = useChatStore((s) => s.stopAgent)

  // We maintain 'showContextPanel' locally as it involves UI preference
  const [showContextPanel, setShowContextPanel] = useState(true)
  const scrollRef = useRef<HTMLDivElement>(null)
  const chatInputRef = useRef<ChatInputAreaHandle>(null)

  // Smart Scroll State
  const [isUserScrolled, setIsUserScrolled] = useState(false)

  // --- Initialization ---
  useEffect(() => {
    // Get initial thread ID from URL if present, or create new
    const params = new URLSearchParams(window.location.search)
    const tid = params.get("thread_id")
    const initId = tid && tid.trim() !== "" ? tid : crypto.randomUUID()

    // Check for message intent
    const pendingMessage = params.get("message")
    const shouldAutoSend = params.get("autoSend") === "true"
    const quoteId = params.get("quoteId")

    // Init Store
    if (projectId) {
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

  // --- Thread List (Sidebar) ---
  // Kept in React Query as it is a list view concern
  const { data: threadsData } = useQuery({
    queryKey: ["projectConversations", projectId],
    queryFn: async () =>
      ConversationsService.listConversations({ projectId: projectId! }),
    enabled: !!projectId,
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

  const handleNewChat = () => {
    const newId = crypto.randomUUID()
    if (projectId) setThread(newId, projectId)
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
      toast.error("Failed to delete chat")
    }
  }

  const handleStopThread = async (id: string) => {
    // If stopping active, use store action. Else API.
    if (id === activeThreadId) {
      await stopAgent()
    } else {
      await AgentService.stopChat({
        requestBody: { thread_id: id, message: "" },
      })
      toast.info("Stopped")
    }
  }

  // --- Side Effect Mutations (Keep here or move to store if generic) ---
  // These are specific to message item actions

  const addToMemoryMutation = useMutation({
    mutationFn: async (text: string) => {
      if (!projectId) throw new Error("No project")
      return MemoryService.addConcept({
        projectId,
        requestBody: {
          name: t("chat.interface.learnedFromChat"),
          description: text,
          related_files: [],
        },
      })
    },
    onSuccess: () => {
      toast.success("Added to Memory")
      queryClient.invalidateQueries({ queryKey: ["projectMemory"] })
    },
  })

  const exportFileMutation = useMutation({
    mutationFn: async (text: string) => {
      if (!projectId) throw new Error("No project")
      const path = prompt(
        t("chat.interface.exportPrompt"),
        "docs/chat-export.md",
      )
      if (!path) return Promise.reject("Cancelled")
      return FilesService.createFile({
        projectId,
        requestBody: { path, content: text },
      })
    },
    onSuccess: () => toast.success(t("chat.interface.exportSuccess")),
  })

  const rewindMutation = useMutation({
    mutationFn: () =>
      ConversationsService.rewindConversation({ threadId: activeThreadId! }),
    onSuccess: () => {
      // Reload store
      if (activeThreadId && projectId) setThread(activeThreadId, projectId)
      toast.success("Rewinded")
    },
  })

  // Phase 6: Retry Logic
  const retryMutation = useMutation({
    mutationFn: async () => {
      if (!activeThreadId) throw new Error("No active thread")
      // Check if AgentService has retryChat (manually added to SDK)
      // @ts-ignore
      return AgentService.retryChat({
        requestBody: {
          thread_id: activeThreadId,
          message: "", // Backend finds the last user message
          project_id: projectId
        }
      })
    },
    onSuccess: () => {
      toast.success(t("chat.interface.retrying", "Retrying from last user message..."))
      // Reload store to reflect rolled back state and new streaming status
      if (activeThreadId && projectId) setThread(activeThreadId, projectId)
    },
    onError: () => {
      toast.error(t("chat.interface.retryFailed", "Retry failed"))
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

  // --- Auto Scroll Logic ---
  // Auto-scroll logic

  // Handle User Scroll Interaction
  const handleScroll = () => {
    if (!scrollRef.current) return
    const { scrollTop, scrollHeight, clientHeight } = scrollRef.current
    // If user is not at the bottom (threshold 50px), mark as user scrolled
    const isAtBottom = scrollHeight - scrollTop - clientHeight < 100
    setIsUserScrolled(!isAtBottom)
  }

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
  }, [isUserScrolled, scrollToBottom, messages, streamedContent, tasks]) // Trigger on content updates

  useEffect(() => {
    setIsUserScrolled(false)
    scrollToBottom()
  }, [scrollToBottom])



  // Phase 8: Deep Linking Listener
  useEffect(() => {
    const handleScrollToRun = (e: CustomEvent<{ runId: string }>) => {
      const runId = e.detail.runId
      // Find DOM element within scroll container
      const el = scrollRef.current?.querySelector(`[data-run-id="${runId}"]`)
      if (el) {
        el.scrollIntoView({ behavior: "smooth", block: "start" })
        // Visual indicator
        el.classList.add("ring-2", "ring-primary/20", "rounded-lg")
        setTimeout(() => el.classList.remove("ring-2", "ring-primary/20", "rounded-lg"), 2000)
      } else {
        toast.info("Message for this step not loaded in view")
      }
    }

    window.addEventListener("chat-scroll-to-run" as any, handleScrollToRun as any)
    return () => {
      window.removeEventListener("chat-scroll-to-run" as any, handleScrollToRun as any)
    }
  }, [])

  return (
    <div className="flex flex-col h-full relative bg-background overflow-hidden">
      <ResizablePanelGroup direction="horizontal" className="h-full w-full">
        {/* Left Sidebar Panel */}
        <ResizablePanel
          defaultSize={20}
          minSize={15}
          maxSize={25}
          className="hidden lg:block min-w-[250px] border-r"
        >
          <ChatSidebar
            threads={threads.map(t => ({
              ...t,
              // Override status if it's the active thread, using reliable store state
              status: t.thread_id === activeThreadId ? status : t.status
            }))}
            activeThreadId={activeThreadId || ""}
            setActiveThreadId={(id) => projectId && setThread(id, projectId)}
            projectId={projectId}
            onDeleteThread={handleDeleteThread}
            onStopThread={handleStopThread}
            onNewChat={handleNewChat}
          />
        </ResizablePanel>

        <ResizableHandle withHandle />

        {/* Center Chat Panel */}
        <ResizablePanel defaultSize={showContextPanel ? 60 : 80} minSize={40}>
          <div className="flex flex-col h-full relative min-h-0">
            {/* Toggle Context Panel Button */}
            {!showContextPanel && (
              <div className="absolute top-4 right-4 z-20">
                <Button
                  variant="ghost"
                  size="icon"
                  onClick={() => setShowContextPanel(true)}
                  title="Open Context Panel"
                >
                  <Brain className="h-5 w-5 text-muted-foreground" />
                </Button>
              </div>
            )}

            {/* HITL Banner - Top of chat area when agent is waiting */}
            <HITLBanner />

            <div
              className="flex-1 overflow-y-auto p-4 min-h-0 scroll-smooth"
              ref={scrollRef}
              onScroll={handleScroll}
              data-tour="chat-messages"
            >
              <div className="space-y-6 max-w-3xl mx-auto pb-4">
                {/* Messages List */}
                {messages.length === 0 && (
                  <div className="flex flex-col items-center justify-center h-full text-muted-foreground mt-20">
                    <Bot size={48} className="mb-4 opacity-20" />
                    <p>{t("chat.interface.startPrompt")}</p>
                  </div>
                )}

                {messages.map((msg) => (
                  <ChatMessageItem
                    key={msg.id}
                    msg={msg}
                    onAddToMemory={(txt) => addToMemoryMutation.mutate(txt)}
                    onExport={(txt) => exportFileMutation.mutate(txt)}
                    onRewind={() => rewindMutation.mutate()}
                    onRetry={() => retryMutation.mutate()}
                    onQuote={() => handleQuoteMessage(msg)}
                  />
                ))}

                {/* Agent Canvas now handles live content - status indicator inline for reference */}
                {status === "running" && (
                  <div className="flex gap-3 justify-start items-start mb-4 max-w-3xl mx-auto animate-in fade-in">
                    <Avatar className="h-8 w-8 mt-1 shrink-0">
                      <AvatarImage src="/bot-avatar.png" />
                      <AvatarFallback>
                        <Bot size={16} />
                      </AvatarFallback>
                    </Avatar>
                    <div className="flex items-center gap-2 py-2">
                      <Loader2 size={14} className="animate-spin text-primary" />
                      <span className="text-sm text-muted-foreground italic">
                        {t("chat.interface.agentWorking", "Agent is working... See details in the side panel →")}
                      </span>
                    </div>
                  </div>
                )}
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
              onSend={sendMessage}
              onStop={stopAgent}
              isAgentWorking={status === "running" || status === "SUMMARIZING"}
              isSending={false} // Store handles optimistic, no separate loading state needed here
              isStopPending={false} // Immediate
              currentProject={currentProject}
              activeThreadId={activeThreadId || undefined}
            />
          </div>
        </ResizablePanel>

        {showContextPanel && (
          <>
            <ResizableHandle withHandle />
            <ResizablePanel
              defaultSize={30}
              minSize={25}
              maxSize={40}
              className="min-w-[320px]"
            >
              <div data-tour="chat-context" className="h-full">
                <ContextPanel
                  projectId={currentProject?.id}
                  activeThreadId={activeThreadId || ""}
                  autoSwitchToTab={undefined} // Disable auto-switch as we have Live Zone now
                  onClose={() => setShowContextPanel(false)}
                />
              </div>
            </ResizablePanel>
          </>
        )}
      </ResizablePanelGroup>
    </div>
  )
}
