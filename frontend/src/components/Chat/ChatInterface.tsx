import { useState, useRef, useEffect } from "react"
import { useTranslation } from "react-i18next"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { AgentService, ProjectsService, MemoryService, FilesService } from "@/client"
import { useSSE } from "@/hooks/useSSE"

import { toast } from "sonner"
import { Button } from "../ui/button"
import { Avatar, AvatarFallback, AvatarImage } from "../ui/avatar"

import { ResizableHandle, ResizablePanel, ResizablePanelGroup } from "@/components/ui/resizable"
import { ContextPanel } from "./ContextPanel"
import { Loader2, Bot, Brain } from "lucide-react"






import { useProjectStore } from "@/stores/projectStore"

import { ChatSidebar, type Thread } from "./ChatSidebar"


import { ChatMessageItem, type Message } from "./ChatMessageItem"
import { TaskSteps } from "./TaskSteps"
import { ChatInputArea } from "./ChatInputArea"

export function ChatInterface() {
    const { t } = useTranslation()
    const { currentProject } = useProjectStore()
    const projectId = currentProject?.id
    const queryClient = useQueryClient()

    // Get initial thread ID from URL if present
    const getInitialThreadId = () => {
        const params = new URLSearchParams(window.location.search)
        const tid = params.get('thread_id')
        return tid && tid.trim() !== '' ? tid : crypto.randomUUID()
    }

    const [messages, setMessages] = useState<Message[]>([])
    const [activeThreadId, setActiveThreadId] = useState<string>(getInitialThreadId)
    const [showContextPanel, setShowContextPanel] = useState(true)
    const [isAgentWorking, setIsAgentWorking] = useState(false)
    const [isSending, setIsSending] = useState(false) // New state to prevent flicker
    const [streamedContent, setStreamedContent] = useState('')  // SSE streamed content

    // SSE Streaming Hook
    useSSE({
        threadId: activeThreadId,
        enabled: isAgentWorking,
        onToken: (token) => setStreamedContent(prev => prev + token),
        onDone: () => {
            setStreamedContent('')
            queryClient.invalidateQueries({ queryKey: ["chatHistory", activeThreadId] })
        }
    })

    // Track local pending messages to prevent flash
    // Map: thread_id -> pending text
    const pendingMessagesRef = useRef<Map<string, string[]>>(new Map())

    const scrollRef = useRef<HTMLDivElement>(null)

    // 1. Fetch Conversation List
    const { data: threadsData } = useQuery({
        queryKey: ["projectConversations", projectId],
        queryFn: async () => {
            if (!projectId) return { conversations: [] }
            return ProjectsService.listProjectConversations({ projectId: projectId })
        },
        enabled: !!projectId,
    })

    const threads = (threadsData as any)?.conversations || []

    // 2. Poll output for Active Thread
    const { data: historyData } = useQuery({
        queryKey: ["chatHistory", activeThreadId],
        queryFn: () => ProjectsService.getConversationHistory({ threadId: activeThreadId }),
        refetchInterval: 1000,
        enabled: !!activeThreadId
    })

    // 3. Poll Activity for Status ("Working...")
    const { data: activityData } = useQuery({
        queryKey: ["chatActivity", activeThreadId],
        queryFn: async () => {
            // Use SDK to fetch activity
            try {
                return await ProjectsService.getConversationActivity({ threadId: activeThreadId })
            } catch (e) {
                return null
            }
        },
        refetchInterval: 1000,
        enabled: !!activeThreadId
    })

    useEffect(() => {
        if (activityData) {
            // Check if status is running
            const status = (activityData as any).status
            const working = status === 'running' || status === 'SUMMARIZING' || status === 'INDEXING' // robustness

            // If we are currently sending, we FORCE working state to stay true 
            // until we see a confirmation from backend or timeout
            if (isSending) {
                if (working) {
                    setIsSending(false) // Backend caught up!
                }
                setIsAgentWorking(true)
            } else {
                setIsAgentWorking(working)
            }
        }
    }, [activityData, isSending])

    // Sync State
    useEffect(() => {
        const data = historyData as any
        if (data && Array.isArray(data.messages)) {
            const formatted: Message[] = data.messages.map((m: any, idx: number) => {
                let content = m.content
                let thinking = m.thinking

                // Parse <think>...</think>
                // Case 1: <think>...</think> Content
                // Case 2: Content <think>...</think> (Unlikely but possible)
                // We assume strict <think> at start if present
                const thinkMatch = content.match(/<think>([\s\S]*?)<\/think>/)
                if (thinkMatch) {
                    thinking = thinkMatch[1].trim()
                    content = content.replace(thinkMatch[0], "").trim()
                }

                return {
                    id: m.id || idx,  // Use backend ID if available
                    role: m.type === 'human' ? 'user' : 'ai',
                    content: content,
                    thinking: thinking,
                    timestamp: m.created_at  // ISO timestamp from backend
                }
            }).filter((m: Message) => (m.content && m.content.trim().length > 0) || (m.thinking && m.thinking.trim().length > 0))

            // --- FLUSH PREVENTION & MERGE ---
            // If backend has new messages, render them.
            // If backend lags behind local pending messages, KEEP local pending messages.

            // Simple heuristic: If last remote message is NOT our pending message, append pending.
            // But we don't know IDs.
            // So we rely on content + role.

            // Logic: Always trust Backend History, BUT if we have local pending messages for this thread,
            // check if they are already in the history.

            const currentPending = pendingMessagesRef.current.get(activeThreadId) || []
            if (currentPending.length > 0) {
                // Check if the last human message in formatted matches the first pending
                // Ideally we clear pending once it appears in history.

                // ROBUSTNESS FIX: Compare trimmed content
                const lastHuman = formatted.slice().reverse().find(m => m.role === 'user')

                if (lastHuman && currentPending.some(p => p.trim() === lastHuman.content.trim())) {
                    // It arrived! Remove from pending (fuzzy match)
                    // We remove specifically the one that matched
                    const matchText = currentPending.find(p => p.trim() === lastHuman.content.trim())
                    const nextPending = currentPending.filter(t => t !== matchText)
                    pendingMessagesRef.current.set(activeThreadId, nextPending)
                }

                // If still pending, append them to formatted (Optimistic UI)
                const pendingRemaining = pendingMessagesRef.current.get(activeThreadId) || []

                pendingRemaining.forEach((txt, i) => {
                    // Double check overlap (simplistic)
                    if (!formatted.some(m => m.role === 'user' && m.content.trim() === txt.trim())) {
                        formatted.push({
                            id: Date.now() + i,
                            role: "user",
                            content: txt
                        })
                    }
                })
            }

            setMessages(formatted)
        } else if (threads.find((t: Thread) => t.thread_id === activeThreadId) === undefined) {
            // New thread
            if (!messages.length) setMessages([])
        }
    }, [historyData, activeThreadId])

    const sendMutation = useMutation({
        mutationFn: (text: string) => AgentService.chatEndpoint({
            requestBody: {
                message: text,
                thread_id: activeThreadId,
                project_id: projectId
            }
        }),
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ["projectConversations"] })
            // Start Working State immediately
            setIsAgentWorking(true)
            // Keep "Sending" state true for a bit to prevent flicker if poll is slow
            setTimeout(() => {
                // Only turn off if backend hasn't picked up yet (handled in poll effect)
                // But we need a failsafe
                setIsSending(false)
            }, 15000)
        },
        onError: () => {
            setMessages(prev => [...prev, { id: Date.now(), role: "ai", content: t('chat.interface.errorSend') }])
            setIsSending(false)
            setIsAgentWorking(false)
        }
    })

    const deleteMutation = useMutation({
        mutationFn: (threadId: string) => ProjectsService.deleteConversation({ conversationId: threadId }),
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ["projectConversations"] })
            if (threads.length > 0) {
                const next = threads[0].thread_id
                setActiveThreadId(next)
            } else {
                handleNewChat()
            }
        }
    })

    const addToMemoryMutation = useMutation({
        mutationFn: async (text: string) => {
            if (!projectId) throw new Error("No project selected")
            return MemoryService.addConcept({
                projectId,
                requestBody: {
                    name: t('chat.interface.learnedFromChat'),
                    description: text,
                    related_files: []
                }
            })
        },
        onSuccess: () => {
            toast.success("Added to Project Memory")
            queryClient.invalidateQueries({ queryKey: ["projectMemory"] })
        },
        onError: (err) => {
            console.error(err)
            toast.error("Failed to add memory")
        }
    })

    const exportFileMutation = useMutation({
        mutationFn: async (text: string) => {
            if (!projectId) throw new Error("No project selected")
            const path = prompt(t('chat.interface.exportPrompt'), "docs/chat-export.md")
            if (!path) return Promise.reject("Cancelled")

            return FilesService.createFile({
                projectId,
                requestBody: {
                    path,
                    content: text
                }
            })
        },
        onSuccess: () => toast.success(t('chat.interface.exportSuccess')),
        onError: (err) => {
            if ((err as any) !== "Cancelled") {
                console.error(err)
                toast.error("Failed to export file")
            }
        }
    })

    const rewindMutation = useMutation({
        mutationFn: () => AgentService.rewindChat({
            requestBody: {
                thread_id: activeThreadId,
                message: ""
            }
        }),
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ["chatHistory"] })
            toast.success(t('chat.interface.rewindSuccess', "Rewinded conversation"))
        },
        onError: (err) => {
            console.error(err)
            toast.error("Failed to rewind")
        }
    })

    const stopMutation = useMutation({
        mutationFn: () => AgentService.stopChat({
            requestBody: {
                thread_id: activeThreadId,
                message: ""
            }
        }),
        onSuccess: () => {
            toast.info(t('chat.interface.stopped', "Generation Stopped"))
            setIsAgentWorking(false)
            setIsSending(false)
            queryClient.invalidateQueries({ queryKey: ["chatHistory"] })
            queryClient.invalidateQueries({ queryKey: ["projectConversations"] })
        },
        onError: (err) => {
            console.error(err)
            toast.error("Failed to stop")
        }
    })

    const handleSend = (text: string) => {
        if (!text.trim() || sendMutation.isPending) return

        // Optimistic & Tracking
        const current = pendingMessagesRef.current.get(activeThreadId) || []
        pendingMessagesRef.current.set(activeThreadId, [...current, text])

        // Immediate Local Render
        setMessages(prev => [...prev, { id: Date.now(), role: "user", content: text }])

        // Set Sending State
        setIsSending(true)
        setIsAgentWorking(true)

        sendMutation.mutate(text)
    }

    const handleNewChat = () => {
        const newId = crypto.randomUUID()
        setActiveThreadId(newId)
        setMessages([])
    }

    // Auto-scroll
    useEffect(() => {
        if (scrollRef.current) {
            scrollRef.current.scrollTop = scrollRef.current.scrollHeight
        }
    }, [messages])

    return (
        <div className="flex flex-col h-full relative bg-background overflow-hidden">
            <ResizablePanelGroup direction="horizontal" className="h-full w-full">
                {/* Left Sidebar Panel */}
                <ResizablePanel defaultSize={20} minSize={15} maxSize={25} className="hidden lg:block min-w-[250px] border-r">
                    <ChatSidebar
                        threads={threads}
                        activeThreadId={activeThreadId}
                        setActiveThreadId={setActiveThreadId}
                        projectId={projectId}
                        onDeleteThread={(id) => deleteMutation.mutate(id)}
                        onStopThread={(id) => {
                            // Stop specific thread
                            AgentService.stopChat({
                                requestBody: { thread_id: id, message: "" }
                            }).then(() => {
                                toast.info(t('chat.interface.stopped'))
                                queryClient.invalidateQueries({ queryKey: ["projectConversations"] })
                            })
                        }}
                        onNewChat={handleNewChat}
                    />
                </ResizablePanel>

                <ResizableHandle withHandle />

                {/* Center Chat Panel */}
                <ResizablePanel defaultSize={showContextPanel ? 60 : 80} minSize={40}>
                    <div className="flex flex-col h-full relative min-h-0">
                        {/* Header/Toolbar (Optional - for toggling Context Panel if closed) */}
                        {!showContextPanel && (
                            <div className="absolute top-4 right-4 z-20">
                                <Button variant="ghost" size="icon" onClick={() => setShowContextPanel(true)} title="Open Context Panel">
                                    <Brain className="h-5 w-5 text-muted-foreground" />
                                </Button>
                            </div>
                        )}

                        <div className="flex-1 overflow-y-auto p-4 min-h-0" ref={scrollRef}>
                            <div className="space-y-6 max-w-3xl mx-auto">
                                {/* Loading Skeleton */}
                                {!historyData && messages.length === 0 && (
                                    <div className="space-y-4 animate-pulse">
                                        {[1, 2, 3].map(i => (
                                            <div key={i} className={`flex gap-3 ${i % 2 === 0 ? 'justify-end' : 'justify-start'}`}>
                                                <div className="h-8 w-8 rounded-full bg-muted" />
                                                <div className={`rounded-lg ${i % 2 === 0 ? 'bg-primary/20' : 'bg-muted'} h-16 w-48`} />
                                            </div>
                                        ))}
                                    </div>
                                )}

                                {/* Empty State */}
                                {historyData && messages.length === 0 ? (
                                    <div className="flex flex-col items-center justify-center h-full text-muted-foreground mt-20">
                                        <Bot size={48} className="mb-4 opacity-20" />
                                        <p>{t('chat.interface.startPrompt')}</p>
                                    </div>
                                ) : messages.map((msg) => (
                                    <ChatMessageItem
                                        key={msg.id}
                                        msg={msg}
                                        onAddToMemory={(txt) => addToMemoryMutation.mutate(txt)}
                                        onExport={(txt) => exportFileMutation.mutate(txt)}
                                        onRewind={() => rewindMutation.mutate()}
                                    />
                                ))}

                                {isAgentWorking && (
                                    <div className="flex flex-col gap-2 max-w-3xl mx-auto animate-in fade-in duration-300 py-4">
                                        {/* 1. Steps (System Activity) - Indented to align with content */}
                                        {(activityData as any)?.tasks?.length > 0 && (
                                            <div className="pl-11 mb-2">
                                                <TaskSteps tasks={(activityData as any).tasks} />
                                            </div>
                                        )}

                                        {/* 2. Ghost Streaming Bubble (The Active Answer) */}
                                        {(() => {
                                            const tasks = (activityData as any)?.tasks || [];
                                            const aiTask = tasks.find((t: any) => t.status === 'running' && t.type === 'ai');

                                            // Prefer SSE streamedContent over polling (aiTask.details)
                                            const displayContent = streamedContent || aiTask?.details

                                            // Case A: AI is streaming text (SSE or polling)
                                            if (displayContent) {
                                                return (
                                                    <div className="flex gap-3 justify-start items-start">
                                                        <Avatar className="h-8 w-8 mt-1 shrink-0">
                                                            <AvatarImage src="/bot-avatar.png" />
                                                            <AvatarFallback><Bot size={16} /></AvatarFallback>
                                                        </Avatar>
                                                        <div className="rounded-lg px-4 py-3 bg-muted text-foreground text-sm leading-relaxed whitespace-pre-wrap shadow-sm min-w-[20px] max-w-[80%]">
                                                            {displayContent}
                                                            <span className="inline-block w-1.5 h-4 bg-primary ml-1 align-middle animate-pulse" />
                                                        </div>
                                                    </div>
                                                )
                                            }

                                            // Case B: Initializing / No Tasks yet / Tool running without streaming text
                                            // If no tasks, show loader. If tasks exist but not AI streaming, we just show steps (handled above).
                                            if (tasks.length === 0) {
                                                return (
                                                    <div className="flex items-center gap-3 pl-11">
                                                        <Loader2 size={14} className="animate-spin text-muted-foreground" />
                                                        <span className="text-sm text-muted-foreground">{t('chat.interface.deepResearching', "Agent initializing...")}</span>
                                                    </div>
                                                )
                                            }

                                            // Case C: Tasks exist but no AI streaming - show current action
                                            const runningTask = tasks.find((t: any) => t.status === 'running')
                                            if (runningTask && !aiTask) {
                                                // Extract meaningful name
                                                let actionName = runningTask.name || 'Working'
                                                actionName = actionName.replace(/^Entering \[|\]$/g, '').replace(/^Exiting \[.*\]$/, '')

                                                return (
                                                    <div className="flex items-center gap-3 pl-11">
                                                        <Loader2 size={14} className="animate-spin text-primary" />
                                                        <span className="text-sm text-muted-foreground">
                                                            {t('chat.interface.workingOn', "Working...")}
                                                            <span className="font-medium text-foreground ml-1">{actionName}</span>
                                                        </span>
                                                    </div>
                                                )
                                            }
                                            return null;
                                        })()}
                                    </div>
                                )}

                                {/* Loading Placeholder for Send Latency */}
                                {sendMutation.isPending && !isAgentWorking && (
                                    <div className="flex gap-3 justify-start max-w-3xl mx-auto opacity-50">
                                        <Avatar className="h-8 w-8 mt-1">
                                            <AvatarFallback><Bot size={16} /></AvatarFallback>
                                        </Avatar>
                                        <div className="rounded-lg px-4 py-3 bg-muted/50 text-muted-foreground text-sm flex items-center gap-2">
                                            <Loader2 size={14} className="animate-spin" /> {t('chat.interface.sending', "Sending...")}
                                        </div>
                                    </div>
                                )}
                            </div>
                        </div>

                        {/* Fixed Input Area */}
                        <ChatInputArea
                            onSend={handleSend}
                            onStop={() => stopMutation.mutate()}
                            isAgentWorking={isAgentWorking}
                            isSending={isSending}
                            isStopPending={stopMutation.isPending}
                            currentProject={currentProject}
                        />
                    </div>
                </ResizablePanel>

                {/* Right Context Panel (Conditional) */}
                {showContextPanel && (
                    <>
                        <ResizableHandle withHandle />
                        <ResizablePanel defaultSize={20} minSize={15} maxSize={30} className="min-w-[300px]">
                            <ContextPanel
                                projectId={currentProject?.id}
                                activeThreadId={activeThreadId}
                                onClose={() => setShowContextPanel(false)}
                            />
                        </ResizablePanel>
                    </>
                )}
            </ResizablePanelGroup>
        </div>
    )
}
