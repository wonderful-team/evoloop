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
import { Send, Loader2, Bot, User, Paperclip, Brain, MoreHorizontal, Save, RotateCcw, Copy } from "lucide-react"
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuTrigger } from "@/components/ui/dropdown-menu"

// Simple type for message
interface Message {
    id: number
    role: "user" | "ai"
    content: string
    thinking?: boolean
}

import { useProjectStore } from "@/stores/projectStore"

import { ChatSidebar, type Thread } from "./ChatSidebar"

export function ChatInterface() {
    const { t } = useTranslation()
    const { currentProject } = useProjectStore()
    const projectId = currentProject?.id
    const queryClient = useQueryClient()
    const [inputValue, setInputValue] = useState("")
    const [isUploading, setIsUploading] = useState(false)
    const [messages, setMessages] = useState<Message[]>([])
    const [activeThreadId, setActiveThreadId] = useState<string>(() => crypto.randomUUID())
    const [showContextPanel, setShowContextPanel] = useState(true)
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
        refetchInterval: 2000,
        enabled: !!activeThreadId
    })

    // Sync State
    useEffect(() => {
        const data = historyData as any
        if (data && Array.isArray(data.messages)) {
            const formatted: Message[] = data.messages.map((m: any, idx: number) => ({
                id: idx,
                role: m.type === 'human' ? 'user' : 'ai',
                content: m.content
            }))
            setMessages(formatted)
        } else if (threads.find((t: Thread) => t.thread_id === activeThreadId) === undefined) {
            // It's a new local thread, only clear if we really intend to reset
            // If we have local messages pending, we might not want to clear
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
        },
        onError: () => {
            setMessages(prev => [...prev, { id: Date.now(), role: "ai", content: t('chat.interface.errorSend') }])
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
                message: "" // Required by type but unused for rewind logic typically, or simplistic stub
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

    const handleSend = () => {
        if (!inputValue.trim() || sendMutation.isPending) return
        const text = inputValue
        setInputValue("")
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
                    <div className="flex flex-col h-full relative">
                        {/* Header/Toolbar (Optional - for toggling Context Panel if closed) */}
                        {!showContextPanel && (
                            <div className="absolute top-4 right-4 z-20">
                                <Button variant="ghost" size="icon" onClick={() => setShowContextPanel(true)} title="Open Context Panel">
                                    <Brain className="h-5 w-5 text-muted-foreground" />
                                </Button>
                            </div>
                        )}

                        <div className="flex-1 p-4 overflow-y-auto" ref={scrollRef}>
                            <div className="space-y-6 max-w-3xl mx-auto pb-24"> {/* Added pb-24 for input area clearance */}
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
                                            <div className={`rounded-lg px-4 py-3 text-sm leading-relaxed whitespace-pre-wrap ${msg.role === 'user' ? 'bg-primary text-primary-foreground' : 'bg-muted text-foreground'}`}>
                                                {msg.content}
                                                {msg.thinking && (
                                                    <div className="flex items-center gap-2 text-muted-foreground italic mt-2">
                                                        <Loader2 size={12} className="animate-spin" /> {t('chat.interface.thinking')}
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

                                {sendMutation.isPending && (
                                    <div className="flex gap-3 justify-start max-w-3xl mx-auto">
                                        <Avatar className="h-8 w-8 mt-1">
                                            <AvatarFallback><Bot size={16} /></AvatarFallback>
                                        </Avatar>
                                        <div className="rounded-lg px-4 py-3 bg-muted text-muted-foreground text-sm flex items-center gap-2">
                                            <Loader2 size={14} className="animate-spin" /> {t('chat.interface.deepResearching')}
                                        </div>
                                    </div>
                                )}
                            </div>
                        </div>

                        {/* Floating Input Area - Positioned absolutely within the Center Panel */}
                        <div className="absolute bottom-6 left-0 right-0 px-4 flex justify-center pointer-events-none z-10">
                            <div className="w-full max-w-3xl bg-background rounded-2xl shadow-xl border border-input p-2 flex items-end gap-2 pointer-events-auto transition-all focus-within:ring-2 focus-within:ring-ring ring-offset-2">
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
                                    onClick={handleSend}
                                    disabled={!inputValue.trim() || sendMutation.isPending || !currentProject || isUploading}
                                    size="icon"
                                    className="mb-0.5 h-9 w-9 rounded-xl shadow-sm"
                                >
                                    <Send size={16} />
                                </Button>
                            </div>
                        </div>

                        {/* Footer Credits */}
                        <div className="absolute bottom-1 left-0 right-0 text-center pointer-events-none">
                            <span className="text-[10px] text-muted-foreground/50">{t('chat.interface.footer')}</span>
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
