import { useState, useRef, useEffect } from "react"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { AgentService, ProjectsService } from "../../client"
import { Button } from "../ui/button"
import { Avatar, AvatarFallback, AvatarImage } from "../ui/avatar"

import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs"
import { FileTree } from "@/components/Files/FileTree"
import { Send, Loader2, Bot, User, Paperclip, MessageSquare, Plus, Trash2 } from "lucide-react"

// Simple type for message
interface Message {
    id: number
    role: "user" | "ai"
    content: string
    thinking?: boolean
}

interface Thread {
    thread_id: string
    title: string
    updated_at: string
}

import { useProjectStore } from "@/stores/projectStore"

export function ChatInterface() {
    const { currentProject } = useProjectStore()
    const projectId = currentProject?.id
    const queryClient = useQueryClient()
    const [inputValue, setInputValue] = useState("")
    const [messages, setMessages] = useState<Message[]>([])
    const [activeThreadId, setActiveThreadId] = useState<string>(() => crypto.randomUUID())
    const scrollRef = useRef<HTMLDivElement>(null)

    // 1. Fetch Conversation List
    const { data: threadsData } = useQuery({
        queryKey: ["projectConversations", projectId],
        queryFn: () => ProjectsService.listProjectConversations({ projectId: projectId! }),
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
            // If new thread (not in list), empty messages
            // But don't empty if we have optimistic updates pending?
            // Actually, if data.messages is empty/undefined, it means no history.
            if (!messages.length) setMessages([])
            // We keep local state for "new" thread until server syncs
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
            setMessages(prev => [...prev, { id: Date.now(), role: "ai", content: "Error: Failed to send message." }])
        }
    })

    const deleteMutation = useMutation({
        mutationFn: (threadId: string) => ProjectsService.deleteConversation({ threadId }),
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
        <div className="flex flex-col h-full relative bg-background">
            {/* Sidebar */}
            {/* Sidebar (Chat History List) - Optional: could be collapsible or separate */}
            <div className="hidden lg:flex w-64 border-r bg-muted/30 flex-col absolute left-0 top-0 bottom-0 z-10">
                <Tabs defaultValue="chats" className="flex-1 flex flex-col">
                    <div className="p-2 border-b bg-muted/10">
                        <TabsList className="w-full grid grid-cols-2">
                            <TabsTrigger value="chats">Chats</TabsTrigger>
                            <TabsTrigger value="files">Files</TabsTrigger>
                        </TabsList>
                    </div>

                    <TabsContent value="chats" className="flex-1 flex flex-col min-h-0 data-[state=inactive]:hidden mt-0">
                        {/* Chat List */}
                        <div className="flex-1 overflow-y-auto p-2 space-y-1">
                            {threads.map((thread: Thread) => (
                                <div
                                    key={thread.thread_id}
                                    className={`group flex items-center justify-between text-sm p-2 rounded-md cursor-pointer hover:bg-muted ${activeThreadId === thread.thread_id ? "bg-muted font-medium" : ""}`}
                                    onClick={() => setActiveThreadId(thread.thread_id)}
                                >
                                    <div className="flex items-center gap-2 truncate max-w-[160px]">
                                        <MessageSquare size={14} className="shrink-0 text-muted-foreground" />
                                        <span className="truncate">{thread.title || "Untitled Conversation"}</span>
                                    </div>
                                    <Button
                                        variant="ghost"
                                        size="icon"
                                        className="h-6 w-6 opacity-0 group-hover:opacity-100 transition-opacity"
                                        onClick={(e) => {
                                            e.stopPropagation()
                                            if (confirm("Delete this conversation?")) deleteMutation.mutate(thread.thread_id)
                                        }}
                                    >
                                        <Trash2 size={12} className="text-muted-foreground hover:text-destructive" />
                                    </Button>
                                </div>
                            ))}
                            {threads.length === 0 && (
                                <div className="p-4 text-xs text-muted-foreground text-center">
                                    No history. Start a chat!
                                </div>
                            )}
                        </div>

                        {/* Bottom Action */}
                        <div className="p-4 border-t mt-auto">
                            <Button onClick={handleNewChat} className="w-full justify-start gap-2" variant="outline">
                                <Plus size={16} /> New Chat
                            </Button>
                        </div>
                    </TabsContent>

                    <TabsContent value="files" className="flex-1 overflow-y-auto min-h-0 data-[state=inactive]:hidden mt-0">
                        <div className="p-2">
                            <FileTree projectId={projectId} />
                        </div>
                    </TabsContent>
                </Tabs>
            </div>

            {/* Main Chat Area */}
            <div className="flex-1 flex flex-col min-w-0 lg:pl-64 relative">
                <div className="flex-1 p-4 overflow-y-auto" ref={scrollRef}>
                    <div className="space-y-6 max-w-3xl mx-auto pb-4">
                        {messages.length === 0 ? (
                            <div className="flex flex-col items-center justify-center h-full text-muted-foreground mt-20">
                                <Bot size={48} className="mb-4 opacity-20" />
                                <p>Start a new conversation...</p>
                            </div>
                        ) : messages.map((msg) => (
                            <div key={msg.id} className={`flex gap-3 ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}>

                                {msg.role === 'ai' && (
                                    <Avatar className="h-8 w-8 mt-1">
                                        <AvatarImage src="/bot-avatar.png" />
                                        <AvatarFallback><Bot size={16} /></AvatarFallback>
                                    </Avatar>
                                )}

                                <div className={`rounded-lg px-4 py-3 max-w-[85%] text-sm leading-relaxed whitespace-pre-wrap ${msg.role === 'user'
                                    ? 'bg-primary text-primary-foreground'
                                    : 'bg-muted text-foreground'
                                    }`}>
                                    {msg.content}
                                    {msg.thinking && (
                                        <div className="flex items-center gap-2 text-muted-foreground italic mt-2">
                                            <Loader2 size={12} className="animate-spin" /> Thinking...
                                        </div>
                                    )}
                                </div>

                                {msg.role === 'user' && (
                                    <Avatar className="h-8 w-8 mt-1">
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
                                    <Loader2 size={14} className="animate-spin" /> Deep Researching...
                                </div>
                            </div>
                        )}
                    </div>
                </div>

                {/* Floating Input Area */}
                <div className="absolute bottom-6 left-0 right-0 px-4 flex justify-center lg:pl-64 pointer-events-none">
                    <div className="w-full max-w-3xl bg-background rounded-2xl shadow-xl border border-input p-2 flex items-end gap-2 pointer-events-auto transition-all focus-within:ring-2 focus-within:ring-ring ring-offset-2">
                        <Button variant="ghost" size="icon" className="shrink-0 mb-1 h-8 w-8 rounded-full">
                            <Paperclip size={18} className="text-muted-foreground" />
                        </Button>
                        <textarea
                            value={inputValue}
                            onChange={(e: React.ChangeEvent<HTMLTextAreaElement>) => setInputValue(e.target.value)}
                            onKeyDown={(e: React.KeyboardEvent<HTMLTextAreaElement>) => {
                                if (e.key === 'Enter' && !e.shiftKey) {
                                    e.preventDefault()
                                    handleSend()
                                }
                            }}
                            placeholder={currentProject ? `Ask about ${currentProject.name}...` : "Select a project to start chatting..."}
                            disabled={!currentProject}
                            className="flex min-h-[44px] w-full bg-transparent border-none focus:ring-0 px-2 py-2.5 text-sm placeholder:text-muted-foreground resize-none focus-visible:outline-none disabled:cursor-not-allowed disabled:opacity-50 max-h-[200px]"
                            rows={1}
                        />
                        <Button
                            onClick={handleSend}
                            disabled={!inputValue.trim() || sendMutation.isPending || !currentProject}
                            size="icon"
                            className="mb-0.5 h-9 w-9 rounded-xl shadow-sm"
                        >
                            <Send size={16} />
                        </Button>
                    </div>
                </div>

                {/* Footer Credits */}
                <div className="absolute bottom-1 left-0 right-0 text-center pointer-events-none lg:pl-64">
                    <span className="text-[10px] text-muted-foreground/50">EvoLoop Gen 3 + Deep Research</span>
                </div>
            </div>
        </div>
    )
}
