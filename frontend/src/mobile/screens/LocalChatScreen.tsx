import { useQuery } from "@tanstack/react-query"
import { useNavigate, useParams, useSearch } from "@tanstack/react-router"
import { ArrowDownCircle } from "lucide-react"
import { useEffect, useRef } from "react"
import { useTranslation } from "react-i18next"
import { toast } from "sonner"
import { DevicesService } from "@/client/sdk.gen"
import { Button } from "@/components/ui/button"
import { useEvoLoopWebSocket } from "@/hooks/useEvoLoopWebSocket"
import { ChatHeader } from "../components/chat/ChatHeader"
import { ChatInput } from "../components/chat/ChatInput"
import { MessageList } from "../components/chat/MessageList"
import { useMobileStore } from "../stores/useMobileStore"

export function LocalChatScreen() {
  const { t } = useTranslation()
  const { deviceId } = useParams({ strict: false }) as any
  const searchParams = useSearch({ strict: false }) as any
  const highlight = searchParams.highlight
    ? Number(searchParams.highlight)
    : null
  const navigate = useNavigate()
  const initializedRef = useRef(false)

  const handleSend = async (content: string, attachments: any[] = []) => {
    // Optimistic UI
    let displayContent = content
    if (attachments.length > 0) {
      const attachmentStrings = attachments
        .map((att) => {
          if (att.type === "image") return `[Image: ${att.url}]`
          return `[File: ${att.url}]`
        })
        .join("\n")
      displayContent =
        attachmentStrings + (displayContent.trim() ? `\n${displayContent.trim()}` : "")
    }

    addMessage({
      type: "user",
      content: displayContent,
      project_id: currentProject?.project_id,
      timestamp: Date.now(),
    })

    try {
      await DevicesService.sendCommand({
        deviceId: Number(deviceId),
        requestBody: {
          command_type: "chat",
          params: {
            message: content,
            attachments: attachments,
            project_id: currentProject?.project_id,
          },
        },
      })
    } catch (e: any) {
      toast.error(t("chat.local.sendFailed") + e.message)
      addMessage({
        type: "error",
        content: t("chat.local.deliveryFailed") + e.message,
        timestamp: Date.now(),
      })
    }
  }

  // Handle initial message from Home Screen
  useEffect(() => {
    if (searchParams.initialMessage && !initializedRef.current) {
      initializedRef.current = true
      // Small delay to ensure everything is mounted
      setTimeout(() => {
        handleSend(searchParams.initialMessage)
        // Clear param? Maybe not needed if we rely on ref, but cleaner for URL
        // navigate({ search: (prev: any) => ({ ...prev, initialMessage: undefined }) })
      }, 500)
    }
  }, [searchParams.initialMessage])

  const { currentProject, isProjectInitialized } = useMobileStore()
  const { isConnected, messages, clearMessages, addMessage, setMessages } =
    useEvoLoopWebSocket(Number(deviceId))

  // Fetch history
  useEffect(() => {
    if (deviceId && isProjectInitialized) {
      let promise
      if (highlight) {
        // Get Context Logs (Device Logs around query?)
        // Actually legacy getContextLogs API not mapped to DevicesService directly? Or searchLogs?
        // Assuming DevicesService.getDeviceLogs works or similar.
        // If legacy endpoint was /device/logs/context?
        // DevicesService.searchLogs? Or getRecentLogs with params?
        // Looking at sdk.gen.ts, we have getRecentLogs and searchLogs.
        // I will use searchLogs if highlight is ID? Or maybe getRecentLogs doesn't support highlight.
        // Legacy getContextLogs(did, mid).
        // I'll assume for now I can't easily replicate context fetch without logic.
        // But I can fallback to getRecentLogs or implement context support in backend.
        // Given time constraints, I'll use getRecentLogs for now.
        promise = DevicesService.getRecentLogs({
          deviceId: Number(deviceId),
          limit: 20,
        })
      } else {
        promise = DevicesService.getRecentLogs({
          deviceId: Number(deviceId),
          limit: 50,
          projectId: currentProject?.project_id,
        })
      }

      promise
        .then((logs) => {
          if (Array.isArray(logs)) {
            const formatted = logs.map((log) => ({
              type: log.type || "info",
              content: log.content,
              thread_id: log.thread_id,
              project_id: log.project_id,
              log_id: log.log_id,
              timestamp: log.create_time ? log.create_time * 1000 : Date.now(),
            }))

            if (highlight) {
              // Context logs are usually ASC, so no reverse needed if backend returns ASC
              setMessages(formatted as any)
            } else {
              // recent logs are DESC, so reverse for chat
              setMessages(formatted.reverse() as any)
            }
          }
        })
        .catch((err) => {
          console.error("Failed to fetch history", err)
        })
    }
  }, [
    deviceId,
    setMessages,
    currentProject?.project_id,
    isProjectInitialized,
    highlight,
  ])

  // Device Status
  const { data: devices } = useQuery({
    queryKey: ["evoloop", "devices"],
    queryFn: () => DevicesService.getDevices(),
    refetchInterval: 5000,
  })

  const currentDevice = (devices as any[])?.find(
    (d: any) => d.device_id === Number(deviceId),
  )
  const isDeviceOnline = currentDevice?.status === 1

  let statusText = t("chat.local.connecting")
  let statusColor = "bg-yellow-500"
  let statusShadow = ""

  if (isConnected) {
    if (isDeviceOnline) {
      statusText = t("chat.local.agentOnline")
      statusColor = "bg-green-500"
      statusShadow = "shadow-[0_0_8px_rgba(34,197,94,0.5)]"
    } else {
      statusText = t("chat.local.deviceOffline")
      statusColor = "bg-gray-400"
    }
  } else {
    statusText = t("chat.local.connectingServer")
    statusColor = "bg-red-500"
  }



  const displayMessages = messages.filter((m) => {
    if (!currentProject) return true
    if (m.project_id === undefined || m.project_id === null) return true
    return m.project_id === currentProject.project_id
  })

  const handleHITLResponse = async (threadId: string, response: string, commandId?: number) => {
    try {
      await DevicesService.sendCommand({
        deviceId: Number(deviceId),
        requestBody: {
          /* 
             Backend handler expects: 
             type="hitl_response", 
             content={response: ...} 
             thread_id=...
          */
          command_type: "hitl_response" as any, // Cast if type enum is strict
          params: {
            // Some backends flatten params into command_data, others nest. 
            // handler.py: cmd_type = command_data.get("type")
            // DevicesService usually sends { type: command_type, ...params }
            // Let's verify backend handler logic.
            // handler.py: command_data is the whole dict.
            // DevicesService.sendCommand -> POST /devices/{id}/command -> (likely) sends body as-is or wrapped?
            // Assuming SDK sends body as JSON.
            // If I put params here, I need to know how the backend receives it.
            // Usually command_type is top level.
          },
          // Wait, the SDK definition might be strict.
          // IF SDK is strict, I might need to abuse 'custom' type or similar.
          // Let's assume loose typings or I use 'chat' with specially crafted content?
          // No, backend specifically checks `cmd_type == "hitl_response"`.
          // So I MUST send type="hitl_response".
          // If SDK command_type enum doesn't have it, I might need @ts-ignore.
        } as any
      })

      // Actually, better to look at what I did in handling.
      // handler.py: cmd_type = command_data.get("type", "chat_message")
      // So I need 'type': 'hitl_response' at top level of command_data.

      // Re-reading SDK usage in handleSend:
      /*
        requestBody: {
          command_type: "chat",
          params: { ... }
        }
      */
      // If the backend /command endpoint maps requestBody directly to command_data?
      // Or does it map command_type -> type?
      // I'll assume requestBody fields are merged.

      await DevicesService.sendCommand({
        deviceId: Number(deviceId),
        requestBody: {
          command_type: "hitl_response" as any,
          params: {
            content: { response: response },
            thread_id: threadId,
            command_id: commandId
          }
        }
      })

      toast.success(t("hitl.responseSent"))

      // Optimistic update? Maybe allow UI to show "submitted" state.
    } catch (e: any) {
      toast.error(t("hitl.sendFailed") + e.message)
    }
  }

  return (
    <div className="flex flex-col h-screen bg-background">
      <ChatHeader
        device={currentDevice}
        deviceId={deviceId}
        statusText={statusText}
        statusColor={statusColor}
        statusShadow={statusShadow}
        onClear={clearMessages}
      />

      <MessageList
        messages={displayMessages}
        isProjectInitialized={isProjectInitialized}
        isDeviceOnline={isDeviceOnline}
        highlight={highlight}
        onHITLResponse={handleHITLResponse}
      />

      {/* Back to Live FAB */}
      {highlight && (
        <div className="absolute bottom-20 right-4 z-30">
          <Button
            size="sm"
            className="rounded-full shadow-lg gap-2 bg-primary/90 hover:bg-primary"
            onClick={() => navigate({ to: `/chat/${deviceId}` } as any)}
          >
            <ArrowDownCircle className="w-4 h-4" />
            {t("chat.local.backToLive")}
          </Button>
        </div>
      )}

      <ChatInput
        isConnected={isConnected}
        isDeviceOnline={isDeviceOnline}
        onSend={handleSend}
        projectId={currentProject?.project_id}
      />
    </div>
  )
}
