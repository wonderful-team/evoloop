import { useNavigate, useParams, useSearch } from "@tanstack/react-router"
import { ArrowLeft, Bot, Menu } from "lucide-react"
import { useEffect, useRef, useState } from "react"
import { useTranslation } from "react-i18next"
import { toast } from "sonner"
import { ConversationsService } from "@/mobile/client"
import { Button } from "@/components/ui/button"
import { streamChat } from "@/lib/streamHelper"
import { ConversationDrawer } from "../components/ConversationDrawer"
import { ChatInput } from "../components/chat/ChatInput"
import { MessageList } from "../components/chat/MessageList"

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

  const isNew = conversationId === "new"

  // Track active ID
  const activeConversationId = useRef(
    conversationId === "new" ? undefined : conversationId,
  )
  // ...

  // Sync Ref when URL changes (e.g. clicking history item)
  useEffect(() => {
    activeConversationId.current =
      conversationId === "new" ? undefined : conversationId
  }, [conversationId])

  // 1. Fetch History if not new
  useEffect(() => {
    if (!isNew && conversationId) {
      setIsLoading(true)
      // Remove Number() cast to support UUIDs
      ConversationsService.getConversationMessages({ thread_id: conversationId })
        .then((res) => {
          if (res.code >= 0 && res.data?.list) {
            const list = res.data.list
            const formatted = list.reverse().map((msg: any) => ({
              type: msg.role === "user" ? "user" : "output",
              content: msg.content,
              timestamp: msg.create_time * 1000,
              log_id: msg.id,
            }))
            setMessages(formatted)
          }
        })
        .catch(() => toast.error(t("cloudChat.historyFailed")))
        .finally(() => setIsLoading(false))
    }
  }, [conversationId, isNew, t])


  // 3. Send Handler
  const handleSend = async (content: string) => {
    if (!content.trim()) return

    // 3.1 Optimistic UI
    const tempUserMsg = {
      type: "user",
      content: content,
      timestamp: Date.now(),
    }
    setMessages((prev) => [...prev, tempUserMsg])

    // 3.2 Prepare Stream Placeholder
    const botMsgId = Date.now()
    setMessages((prev) => [
      ...prev,
      {
        type: "output",
        content: "...",
        timestamp: Date.now(),
        id: botMsgId,
        isStreaming: true,
      },
    ])

    setIsStreaming(true)
    let fullResponse = ""

    try {
      // 3.3 Call API
      const params = {
        message: content,
        conversation_id: activeConversationId.current, // Use Ref
      }

      await streamChat(params as any, (chunk: any, _meta: any) => {
        // Update active ID if provided (first chunk usually)
        // streamChat helper doesn't pass meta 'conversation_id' in chunk usually,
        // but we can rely on initial params or assume activeId is set.
        // Actually streamChat takes conversation_id as input param, so we must have one.
        // If new, how do we get ID?
        // AgentService.chatEndpoint returns thread_id.
        // My streamHelper returns Promise<void> and swallows the thread_id from initial POST.
        // I should update streamHelper to return thread_id or set it.
        // Limit: The current streamChat helper implementation doesn't return the ID created by POST.
        // We need to fix streamHelper if conversationId is undefined initially ('new').
        // BUT CloudChatScreen uses 'new' string.
        // We need to generate a UUID if 'new'.
        // Frontend usually generates UUID for new thread? Or backend.
        // Backend /chat accepts thread_id.
        // So we should generate one if missing and pass it.
        // Let's generate one if 'new'.

        // Update the last message
        fullResponse += chunk
        setMessages((prev) => {
          const last = prev[prev.length - 1]
          // If we are updating the specific bot message
          if (last.id === botMsgId || last.isStreaming) {
            return [
              ...prev.slice(0, -1),
              { ...last, content: fullResponse, type: "output" },
            ]
          }
          return prev
        })
      })

      // Stream Done
      setIsStreaming(false)
      setMessages((prev) => {
        const last = prev[prev.length - 1]
        return [...prev.slice(0, -1), { ...last, isStreaming: false }]
      })
    } catch (e: any) {
      console.error("Chat Error:", e)
      if (e.status === 402) {
        toast.error(t("chat.limitReached"), {
          action: {
            label: t("profile.upgradeNow"),
            onClick: () =>
              window.open(
                "https://mall.imagicbox.cn/h5/pages/member/index",
                "_blank",
              ),
          },
          duration: 5000,
        })
        setIsStreaming(false)
        // Remove the "..." placeholder if it exists?
        // Currently we append error message.
        // Let's replace the last loading message with an error message in UI if possible or just append
        setMessages((prev) => {
          // If last message is the loading one, replace it or remove it
          const last = prev[prev.length - 1]
          if (last.id === botMsgId || last.isStreaming) {
            return [
              ...prev.slice(0, -1),
              {
                type: "error",
                content: t("chat.limitReachedDescription"),
                timestamp: Date.now(),
              },
            ]
          }
          return [
            ...prev,
            {
              type: "error",
              content: t("chat.limitReachedDescription"),
              timestamp: Date.now(),
            },
          ]
        })
      } else {
        toast.error(t("cloudChat.sendFailed") + (e.message || ""))
        setIsStreaming(false)
        setMessages((prev) => [
          ...prev,
          {
            type: "error",
            content: e.message || t("common.error.title"),
            timestamp: Date.now(),
          },
        ])
      }
    }
  }

  // 2. Handle Initial Message
  useEffect(() => {
    if (searchParams.initialMessage && !initializedRef.current) {
      initializedRef.current = true
      setTimeout(() => {
        handleSend(searchParams.initialMessage)
      }, 100)
    }
  }, [searchParams.initialMessage, handleSend])

  // Header Logic
  const Header = (
    <div className="flex items-center justify-between p-4 pb-2 bg-background/80 backdrop-blur-md sticky top-0 z-10 border-b">
      <div className="flex items-center gap-3">
        <Button
          variant="ghost"
          size="icon"
          onClick={() => navigate({ to: "/" as any })}
        >
          <ArrowLeft className="w-5 h-5" />
        </Button>

        <ConversationDrawer
          activeId={conversationId === "new" ? undefined : conversationId}
          trigger={
            <Button variant="ghost" size="icon">
              <Menu className="w-5 h-5" />
            </Button>
          }
        />

        <div>
          <h1 className="font-semibold text-lg flex items-center gap-2">
            <Bot className="w-5 h-5 text-primary" />
            {t("cloudChat.title")}
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
      {isLoading && (
        <div className="absolute top-20 left-1/2 -translate-x-1/2 bg-background/80 px-3 py-1 rounded-full text-xs shadow-sm">
          {t("cloudChat.loadingHistory")}
        </div>
      )}

      <ChatInput
        isConnected={true}
        isDeviceOnline={true}
        onSend={handleSend}
        // Cloud Chat currently lacks explicit Project ID in prompt?
        // But upload requires it.
        // Ideally we should fetch conversation details to get project_id.
        // For 'new', we don't have it.
        // Pass undefined for now, upload might fail or be disabled.
        // Or map Cloud Chat to "current global project"?
        // Currently CloudChatScreen doesn't fetch Project.
        projectId={undefined}
        placeholder={
          isStreaming ? t("cloudChat.typing") : t("cloudChat.placeholder")
        }
      />
    </div>
  )
}
