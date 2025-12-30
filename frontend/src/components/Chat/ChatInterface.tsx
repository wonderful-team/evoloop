import { useState, useRef, useEffect } from "react"
import { useTranslation } from "react-i18next"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { AgentService, ProjectsService, MemoryService, FilesService } from "@/client"
import { EvoLoopApi } from "@/client/evoloopClient"
import { toast } from "sonner"
import { Button } from "../ui/button"
import { Avatar, AvatarFallback, AvatarImage } from "../ui/avatar"

import { ResizableHandle, ResizablePanel, ResizablePanelGroup } from "@/components/ui/resizable"
import { ContextPanel } from "./ContextPanel"
import { Send, Loader2, Bot, User, Paperclip, Brain, MoreHorizontal, Save, RotateCcw, Copy, ChevronDown, Square } from "lucide-react"
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuTrigger } from "@/components/ui/dropdown-menu"
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from "@/components/ui/collapsible"

// Simple type for message
interface Message {
    id: number
    role: "user" | "ai"
    content: string
    thinking?: string
}

import { useProjectStore } from "@/stores/projectStore"

import { ChatSidebar, type Thread } from "./ChatSidebar"
import { MessageContent } from "./MessageContent"

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

    const [inputValue, setInputValue] = useState("")
    const [isUploading, setIsUploading] = useState(false)
    const [messages, setMessages] = useState<Message[]>([])
    const [activeThreadId, setActiveThreadId] = useState<string>(getInitialThreadId)
    const [showContextPanel, setShowContextPanel] = useState(true)
    const [isAgentWorking, setIsAgentWorking] = useState(false)

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
            const working = (activityData as any).status === 'running'
            setIsAgentWorking(working)
        }
    }, [activityData])

    // Sync State
    useEffect(() => {
        const data = historyData as any
        if (data && Array.isArray(data.messages)) {
            const formatted: Message[] = data.messages.map((m: any, idx: number) => {
                let content = m.content
                let thinking = undefined

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
                    id: idx,
                    role: m.type === 'human' ? 'user' : 'ai',
                    content: content,
                    thinking: thinking
                }
            })

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

                const lastHuman = formatted.slice().reverse().find(m => m.role === 'user')

                if (lastHuman && currentPending.includes(lastHuman.content)) {
                    // It arrived! Remove from pending
                    const nextPending = currentPending.filter(t => t !== lastHuman.content)
                    pendingMessagesRef.current.set(activeThreadId, nextPending)
                }

                // If still pending, append them to formatted (Optimistic UI)
                // Note: This logic assumes pending messages are strictly strictly sequential after history.
                // It might duplicate if there is a partial match or lag.
                // Safer: Just append all remaining pending messages that are NOT in formatted.
                const pendingRemaining = pendingMessagesRef.current.get(activeThreadId) || []

                pendingRemaining.forEach((txt, i) => {
                    // Double check overlap (simplistic)
                    if (!formatted.some(m => m.role === 'user' && m.content === txt)) {
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
        },
        onError: () => {
            setMessages(prev => [...prev, { id: Date.now(), role: "ai", content: t('chat.interface.errorSend') }])
            // Remove from pending on error?
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
            queryClient.invalidateQueries({ queryKey: ["chatHistory"] })
        },
        onError: (err) => {
            console.error(err)
            toast.error("Failed to stop")
        }
    })

    const handleSend = () => {
        if (!inputValue.trim() || sendMutation.isPending) return
        const text = inputValue
        setInputValue("")

        // Optimistic & Tracking
        const current = pendingMessagesRef.current.get(activeThreadId) || []
        pendingMessagesRef.current.set(activeThreadId, [...current, text])

        // Immediate Local Render
        setMessages(prev => [...prev, { id: Date.now(), role: "user", content: text }])

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
                                {messages.length === 0 ? (
                                    <div className="flex flex-col items-center justify-center h-full text-muted-foreground mt-20">
                                        <Bot size={48} className="mb-4 opacity-20" />
                                        <p>{t('chat.interface.startPrompt')}</p>
                                    </div>
                                ) : messages.map((msg) => (
                                    <div key={msg.id} className={`group flex gap-3 ${msg.role === 'user' ? 'justify-end' : 'justify-start'} items-start`}>
                                        {msg.role === 'ai' && (
                                            <Avatar className="h-8 w-8 mt-1 shrink-0">
                                                <AvatarImage src="/bot-avatar.png" />
                                                <AvatarFallback><Bot size={16} /></AvatarFallback>
                                            </Avatar>
                                        )}

                                        <div className={`relative max-w-[85%]`}>
                                            <div className="flex flex-col gap-1">
                                                {/* Reasoning/Thinking Block */}
                                                {msg.thinking && (
                                                    <Collapsible defaultOpen={false} className="w-full">
                                                        <CollapsibleTrigger asChild>
                                                            <Button variant="ghost" size="sm" className="h-6 p-0 text-muted-foreground hover:bg-transparent flex items-center gap-1 text-xs">
                                                                <Brain size={12} />
                                                                <span className="italic">{t('chat.interface.thinkingProcess', "Reasoning Process")}</span>
                                                                <ChevronDown size={12} className="opacity-50" />
                                                            </Button>
                                                        </CollapsibleTrigger>
                                                        <CollapsibleContent className="text-xs text-muted-foreground bg-muted/30 p-2 rounded-md mb-2 border-l-2 border-primary/20 whitespace-pre-wrap">
                                                            {msg.thinking}
                                                        </CollapsibleContent>
                                                    </Collapsible>
                                                )}

                                                {/* Main Content */}
                                                {(msg.content || !msg.thinking) && (
                                                    <div className={`rounded-lg px-4 py-3 text-sm leading-relaxed ${msg.role === 'user' ? 'bg-primary text-primary-foreground' : 'bg-muted text-foreground'}`}>
                                                        <MessageContent content={msg.content} />
                                                    </div>
                                                )}
                                            </div>

                                            {/* Message Actions */}
                                            <div className={`absolute -top-2 ${msg.role === 'user' ? '-left-10' : '-right-10'} opacity-0 group-hover:opacity-100 transition-opacity`}>
                                                <DropdownMenu>
                                                    <DropdownMenuTrigger asChild>
                                                        <Button variant="ghost" size="icon" className="h-8 w-8 rounded-full bg-background border shadow-sm">
                                                            <MoreHorizontal className="h-4 w-4" />
                                                        </Button>
                                                    </DropdownMenuTrigger>
                                                    <DropdownMenuContent>
                                                        <DropdownMenuItem onClick={() => navigator.clipboard.writeText(msg.content)}>
                                                            <Copy className="mr-2 h-4 w-4" /> {t('chat.interface.copy')}
                                                        </DropdownMenuItem>
                                                        {msg.role === 'ai' && (
                                                            <>
                                                                <DropdownMenuItem onClick={() => addToMemoryMutation.mutate(msg.content)}>
                                                                    <Brain className="mr-2 h-4 w-4" /> {t('chat.interface.memorize')}
                                                                </DropdownMenuItem>
                                                                <DropdownMenuItem onClick={() => exportFileMutation.mutate(msg.content)}>
                                                                    <Save className="mr-2 h-4 w-4" /> {t('chat.interface.export')}
                                                                </DropdownMenuItem>
                                                                <DropdownMenuItem onClick={() => rewindMutation.mutate()}>
                                                                    <RotateCcw className="mr-2 h-4 w-4" /> {t('chat.interface.rewind')}
                                                                </DropdownMenuItem>
                                                            </>
                                                        )}
                                                    </DropdownMenuContent>
                                                </DropdownMenu>
                                            </div>
                                        </div>

                                        {msg.role === 'user' && (
                                            <Avatar className="h-8 w-8 mt-1 shrink-0">
                                                <AvatarFallback><User size={16} /></AvatarFallback>
                                            </Avatar>
                                        )}
                                    </div>
                                ))}

                                {isAgentWorking && (
                                    <div className="flex gap-3 justify-start max-w-3xl mx-auto animate-pulse">
                                        <Avatar className="h-8 w-8 mt-1">
                                            <AvatarFallback><Bot size={16} /></AvatarFallback>
                                        </Avatar>
                                        <div className="rounded-lg px-4 py-3 bg-muted text-muted-foreground text-sm flex items-center gap-2">
                                            <Loader2 size={14} className="animate-spin" /> {t('chat.interface.deepResearching', "Agent working...")}
                                        </div>
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
                        <div className="shrink-0 p-4 pt-2 bg-background/95 backdrop-blur supports-[backdrop-filter]:bg-background/60">
                            <div className="w-full max-w-3xl mx-auto">
                                <div className="bg-background rounded-2xl shadow-sm border border-input p-2 flex items-end gap-2 transition-all focus-within:ring-2 focus-within:ring-ring ring-offset-2">
                                    <Button variant="ghost" size="icon" className="shrink-0 mb-1 h-8 w-8 rounded-full" onClick={() => document.getElementById('file-upload')?.click()} disabled={isUploading}>
                                        {isUploading ? <Loader2 size={18} className="animate-spin text-muted-foreground" /> : <Paperclip size={18} className="text-muted-foreground" />}
                                    </Button>
                                    <input
                                        type="file"
                                        id="file-upload"
                                        className="hidden"
                                        onChange={async (e) => {
                                            const file = e.target.files?.[0]
                                            if (!file) return

                                            setIsUploading(true)
                                            try {
                                                const url = await EvoLoopApi.uploadFile(file)
                                                setInputValue(prev => prev + (prev ? "\n" : "") + `[File: ${url}]`)
                                                toast.success(t('chat.interface.uploadSuccess'))
                                            } catch (error) {
                                                toast.error(t('chat.interface.uploadError'))
                                                console.error(error)
                                            } finally {
                                                setIsUploading(false)
                                                // Reset input
                                                e.target.value = ''
                                            }
                                        }}
                                    />
                                    <textarea
                                        value={inputValue}
                                        onChange={(e: React.ChangeEvent<HTMLTextAreaElement>) => setInputValue(e.target.value)}
                                        onKeyDown={(e: React.KeyboardEvent<HTMLTextAreaElement>) => {
                                            if (e.key === 'Enter' && !e.shiftKey) {
                                                e.preventDefault()
                                                handleSend()
                                            }
                                        }}
                                        placeholder={currentProject ? t('chat.interface.askProject', { project: currentProject.name }) : t('chat.interface.selectProject')}
                                        disabled={!currentProject}
                                        className="flex min-h-[44px] w-full bg-transparent border-none focus:ring-0 px-2 py-2.5 text-sm placeholder:text-muted-foreground resize-none focus-visible:outline-none disabled:cursor-not-allowed disabled:opacity-50 max-h-[200px]"
                                        rows={1}
                                    />
                                    <Button
                                        onClick={() => {
                                            if (isAgentWorking) {
                                                stopMutation.mutate()
                                            } else {
                                                handleSend()
                                            }
                                        }}
                                        disabled={(!inputValue.trim() && !isAgentWorking) || sendMutation.isPending || !currentProject || isUploading}
                                        size="icon"
                                        className={`mb-0.5 h-9 w-9 rounded-xl shadow-sm transition-all ${isAgentWorking ? "bg-red-500 hover:bg-red-600 text-white animate-pulse" : ""}`}
                                        title={isAgentWorking ? t('chat.interface.stop', "Stop Generating") : t('chat.interface.send', "Send Message")}
                                    >
                                        {isAgentWorking || stopMutation.isPending ? (
                                            stopMutation.isPending ? <Loader2 size={16} className="animate-spin" /> : <Square size={16} fill="currentColor" />
                                        ) : (
                                            <Send size={16} />
                                        )}
                                    </Button>
                                </div>
                            </div>
                        </div>
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
