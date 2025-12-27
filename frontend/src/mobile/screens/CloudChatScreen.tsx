
import { useParams, useSearch } from "@tanstack/react-router"
import { EvoLoopApi, AIMessage } from "@/client/evoloopClient"
import { useEffect, useState, useRef } from "react"
import { toast } from "sonner"
import { MessageList } from "../components/chat/MessageList"
import { ChatInput } from "../components/chat/ChatInput"
import { Button } from "@/components/ui/button"
import { ArrowLeft, MoreHorizontal, Bot } from "lucide-react"
import { useNavigate } from "@tanstack/react-router"


export function CloudChatScreen() {
    const { conversationId } = useParams({ strict: false }) as any
    const searchParams = useSearch({ strict: false }) as any
    const navigate = useNavigate()

    // State
    const [messages, setMessages] = useState<any[]>([])
    // Default from storage or fallback

    const [isLoading, setIsLoading] = useState(false)
    const [isStreaming, setIsStreaming] = useState(false)
    const initializedRef = useRef(false)

    const isNew = conversationId === 'new'

    // Fetch Models on Mount


    // 1. Fetch History if not new
    useEffect(() => {
        if (!isNew && conversationId) {
            setIsLoading(true)
            EvoLoopApi.AI.getMessages(Number(conversationId), 1, 50)
                .then(res => {
                    // Backend returns newest first (id desc), usually UI needs oldest first for chat flow?
                    // ChatScreen reverses them. Let's see MessageList.
                    // MessageList renders top to bottom.
                    // If we get [Newest, ..., Oldest], we need to reverse to [Oldest, ..., Newest].
                    const list = res.list || []
                    const formatted = list.reverse().map(msg => ({
                        type: msg.role === 'user' ? 'user' : 'output', // Map 'assistant' to 'output' for MessageList compat
                        content: msg.content,
                        timestamp: msg.create_time * 1000,
                        log_id: msg.id
                    }))
                    setMessages(formatted)
                })
                .catch(() => toast.error("Failed to load history"))
                .finally(() => setIsLoading(false))
        }
    }, [conversationId, isNew])

    // 2. Handle Initial Message
    useEffect(() => {
        if (searchParams.initialMessage && !initializedRef.current) {
            initializedRef.current = true
            // Allow a small tick for mounting
            setTimeout(() => {
                handleSend(searchParams.initialMessage)
            }, 100)
        }
    }, [searchParams.initialMessage])

    // 3. Send Handler
    const handleSend = async (content: string) => {
        if (!content.trim()) return

        // 3.1 Optimistic UI
        const tempUserMsg = {
            type: 'user',
            content: content,
            timestamp: Date.now()
        }
        setMessages(prev => [...prev, tempUserMsg])

        // 3.2 Prepare Stream Placeholder
        const botMsgId = Date.now()
        setMessages(prev => [...prev, {
            type: 'thought', // Use thought as placeholder or output? 'output' is final. 'thought' usually implies processing. 
            // Let's use 'output' but with isThinking? MessageList might not support streaming status well.
            // Let's assume 'output' is fine.
            content: "...",
            timestamp: Date.now(),
            id: botMsgId,
            isStreaming: true
        }])

        setIsStreaming(true)
        let fullResponse = ""

        try {
            // 3.3 Call API
            const finalParams = {
                message: content,
                conversation_id: isNew ? undefined : conversationId, // 'new' or ID
                stream: true
            }

            await EvoLoopApi.AI.chat(finalParams, (chunk) => {
                // Update the last message
                fullResponse += chunk
                setMessages(prev => {
                    const last = prev[prev.length - 1]
                    // If we are updating the specific bot message
                    if (last.id === botMsgId || last.isStreaming) {
                        return [
                            ...prev.slice(0, -1),
                            { ...last, content: fullResponse, type: 'output' }
                        ]
                    }
                    return prev
                })

                // If meta has conversation_id and we are in 'new' mode, redirect?
                // Actually changing URL mid-chat might unmount. 
                // Better to just keep 'new' in URL until user leaves, or silent update?
                // Let's stick to 'new' state for now.
            })

            // Stream Done
            setIsStreaming(false)
            setMessages(prev => {
                const last = prev[prev.length - 1]
                return [
                    ...prev.slice(0, -1),
                    { ...last, isStreaming: false }
                ]
            })

        } catch (e: any) {
            toast.error("Failed to send: " + e.message)
            setIsStreaming(false)
            setMessages(prev => [...prev, { type: 'error', content: e.message, timestamp: Date.now() }])
        }
    }

    // Header Logic
    const Header = (
        <div className="flex items-center justify-between p-4 pb-2 bg-background/80 backdrop-blur-md sticky top-0 z-10 border-b">
            <div className="flex items-center gap-3">
                <Button variant="ghost" size="icon" onClick={() => navigate({ to: '/' as any })}>
                    <ArrowLeft className="w-5 h-5" />
                </Button>
                <div>
                    <h1 className="font-semibold text-lg flex items-center gap-2">
                        <Bot className="w-5 h-5 text-primary" />
                        Cloud Agent
                    </h1>

                </div>
            </div>
            <Button variant="ghost" size="icon">
                <MoreHorizontal className="w-5 h-5" />
            </Button>
        </div>
    )

    return (
        <div className="flex flex-col h-screen bg-background">
            {Header}

            <MessageList
                messages={messages}
                isProjectInitialized={true} // Always true for Cloud
                isDeviceOnline={true} // Always true for Cloud
                highlight={null}
            />
            {isLoading && <div className="absolute top-20 left-1/2 -translate-x-1/2 bg-background/80 px-3 py-1 rounded-full text-xs shadow-sm">Loading history...</div>}

            <ChatInput
                isConnected={true}
                isDeviceOnline={true}
                onSend={handleSend}
                placeholder={isStreaming ? "AI is typing..." : "Ask Cloud AI..."}
            />
        </div>
    )
}
