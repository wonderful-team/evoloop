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
import { ChatInputArea } from "./ChatInputArea"
import { ChatMessageItem } from "./ChatMessageItem"
import { ChatSidebar, type Thread } from "./ChatSidebar"
import { ContextPanel } from "./ContextPanel"
import { HumanRequestCard } from "./HumanRequestCard"
import { MessageContent } from "./MessageContent"
import { TaskSteps } from "./TaskSteps"

const CompositeAIBubble = memo(() => {
  const streamedContent = useChatStore((s) => s.streamedContent)
  const tasks = useChatStore((s) => s.tasks)
  const status = useChatStore((s) => s.status)

  // Only show when there's activity (streaming content or running tasks)
  const hasContent =
    streamedContent || tasks.some((t) => t.status === "running")
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
  const status = useChatStore((s) => s.status)
  const tasks = useChatStore((s) => s.tasks)

  if (status !== "running" && status !== "SUMMARIZING") return null

  // Find active task name
  const runningTask = tasks.find((t: any) => t.status === "running")
  const actionName = runningTask ? runningTask.name : "Working..."

  return (
    <div className="flex items-center gap-3 pl-11 mb-4">
      <Loader2 size={14} className="animate-spin text-primary" />
      <span className="text-sm text-muted-foreground">{actionName}</span>
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
  const humanRequest = useChatStore((s) => s.humanRequest) // New selector
  // streamedContent is handled by StreamingBubble
  const setThread = useChatStore((s) => s.setThread)
  const sendMessage = useChatStore((s) => s.sendMessage)
  const stopAgent = useChatStore((s) => s.stopAgent)

  // We maintain 'showContextPanel' locally as it involves UI preference
  const [showContextPanel, setShowContextPanel] = useState(true)
  const scrollRef = useRef<HTMLDivElement>(null)

  // Smart Scroll State
  const [isUserScrolled, setIsUserScrolled] = useState(false)

  // --- Initialization ---
  useEffect(() => {
    // Get initial thread ID from URL if present, or create new
    const params = new URLSearchParams(window.location.search)
    const tid = params.get("thread_id")
    const initId = tid && tid.trim() !== "" ? tid : crypto.randomUUID()

    // Init Store
    if (projectId) {
      setThread(initId, projectId)
    }
  }, [projectId, setThread]) // Run once when project loads

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
  }, [isUserScrolled, scrollToBottom]) // Trigger on updates

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
            threads={threads}
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

            <div
              className="flex-1 overflow-y-auto p-4 min-h-0 scroll-smooth"
              ref={scrollRef}
              onScroll={handleScroll}
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
                  />
                ))}

                {/* Composite AI Bubble - Shows TaskSteps + Streaming Content together */}
                {status !== "idle" &&
                  status !== "stopped" &&
                  status !== "unknown" &&
                  status !== "interrupted" && (
                    <div className="flex flex-col gap-2 max-w-3xl mx-auto animate-in fade-in duration-300">
                      <CompositeAIBubble />
                      <StatusIndicator />
                    </div>
                  )}

                {/* Show collapsed TaskSteps when idle but tasks exist (Persistence after completion) */}
                {status === "idle" && tasks.length > 0 && (
                  <div className="flex gap-3 justify-start items-start mb-4 max-w-3xl mx-auto">
                    <Avatar className="h-8 w-8 mt-1 shrink-0 opacity-50">
                      <AvatarFallback>
                        <Bot size={16} />
                      </AvatarFallback>
                    </Avatar>
                    <Collapsible defaultOpen={false} className="flex-1">
                      <CollapsibleTrigger asChild>
                        <Button
                          variant="ghost"
                          size="sm"
                          className="h-6 p-0 text-muted-foreground hover:bg-transparent flex items-center gap-1 text-xs"
                        >
                          <ChevronDown size={12} className="opacity-50" />
                          <span className="italic">
                            {tasks.filter((t) => t.status === "done").length}/
                            {tasks.length} steps completed
                          </span>
                        </Button>
                      </CollapsibleTrigger>
                      <CollapsibleContent className="mt-1">
                        <TaskSteps tasks={tasks} />
                      </CollapsibleContent>
                    </Collapsible>
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

            {/* Interrupted State Banner (REMOVED - migrated to HumanRequestCard) */}
            {humanRequest && status === "interrupted" && (
              <HumanRequestCard request={humanRequest} />
            )}

            {/* Input Area */}
            <ChatInputArea
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
              defaultSize={20}
              minSize={15}
              maxSize={30}
              className="min-w-[300px]"
            >
              <ContextPanel
                projectId={currentProject?.id}
                activeThreadId={activeThreadId || ""}
                onClose={() => setShowContextPanel(false)}
              />
            </ResizablePanel>
          </>
        )}
      </ResizablePanelGroup>

      {/* Removed HumanInputDialog */}
    </div>
  )
}
