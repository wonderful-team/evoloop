import { ConversationDrawer } from "../components/ConversationDrawer"
import { useTranslation } from "react-i18next"
import { Menu, Bot, ArrowLeft } from "lucide-react"
import { useParams, useSearch, useNavigate } from "@tanstack/react-router"
import { EvoLoopApi } from "@/client/evoloopClient"
import { useEffect, useState, useRef } from "react"
import { toast } from "sonner"
import { MessageList } from "../components/chat/MessageList"
import { ChatInput } from "../components/chat/ChatInput"
import { Button } from "@/components/ui/button"

export function CloudChatScreen() {
    const { t } = useTranslation()
    const { conversationId } = useParams({ strict: false }) as any
    const searchParams = useSearch({ strict: false }) as any
    const navigate = useNavigate()

    // State
    const [messages, setMessages] = useState<any[]>([])

    const [isLoading, setIsLoading] = useState(false)
    const [isStreaming, setIsStreaming] = useState(false)
    const initializedRef = useRef(false)

    const isNew = conversationId === 'new'

    // Track active ID
    const activeConversationId = useRef(conversationId === 'new' ? undefined : conversationId)
    // ...

    // Sync Ref when URL changes (e.g. clicking history item)
    useEffect(() => {
        activeConversationId.current = conversationId === 'new' ? undefined : conversationId
    }, [conversationId])

    // 1. Fetch History if not new
    useEffect(() => {
        if (!isNew && conversationId) {
            setIsLoading(true)
            EvoLoopApi.AI.getMessages(Number(conversationId), 1, 50)
                .then(res => {
                    const list = res.list || []
                    const formatted = list.reverse().map((msg: any) => ({
                        type: msg.role === 'user' ? 'user' : 'output',
                        content: msg.content,
                        timestamp: msg.create_time * 1000,
                        log_id: msg.id
                    }))
                    setMessages(formatted)
                })
                .catch(() => toast.error(t('cloudChat.historyFailed')))
                .finally(() => setIsLoading(false))
        }
    }, [conversationId, isNew])

    // 2. Handle Initial Message
    useEffect(() => {
        if (searchParams.initialMessage && !initializedRef.current) {
            initializedRef.current = true
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
            type: 'output',
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
                conversation_id: activeConversationId.current, // Use Ref
                stream: true
            }

            await EvoLoopApi.AI.chat(finalParams, (chunk, meta) => {
                // Update active ID if provided (first chunk usually)
                if (meta?.conversation_id && !activeConversationId.current) {
                    activeConversationId.current = meta.conversation_id
                }

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
            toast.error(t('cloudChat.sendFailed') + e.message)
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

                <ConversationDrawer
                    activeId={conversationId === 'new' ? undefined : Number(conversationId)}
                    trigger={
                        <Button variant="ghost" size="icon">
                            <Menu className="w-5 h-5" />
                        </Button>
                    }
                />

                <div>
                    <h1 className="font-semibold text-lg flex items-center gap-2">
                        <Bot className="w-5 h-5 text-primary" />
                        {t('cloudChat.title')}
                    </h1>
                </div>
            </div>
            <div />
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
            {isLoading && <div className="absolute top-20 left-1/2 -translate-x-1/2 bg-background/80 px-3 py-1 rounded-full text-xs shadow-sm">{t('cloudChat.loadingHistory')}</div>}

            <ChatInput
                isConnected={true}
                isDeviceOnline={true}
                onSend={handleSend}
                placeholder={isStreaming ? t('cloudChat.typing') : t('cloudChat.placeholder')}
            />
        </div>
    )
}
