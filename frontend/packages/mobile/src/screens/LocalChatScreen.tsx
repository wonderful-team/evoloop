import { useQuery } from "@tanstack/react-query"
import { useNavigate, useParams, useSearch } from "@tanstack/react-router"
import { ArrowDownCircle } from "lucide-react"
import { useEffect, useRef, useState } from "react"
import { useTranslation } from "react-i18next"
import { toast } from "sonner"
import { DevicesService, CommandService, LogsService } from "../client"
import { Button } from "@evoloop/shared/components/ui/button"
import { useEvoLoopWebSocket } from "../hooks/useEvoLoopWebSocket"
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
  const [activeThreadId, setActiveThreadId] = useState<string | undefined>(undefined)

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
      await CommandService.sendCommand({
        device_id: Number(deviceId),
        content: {
          command_type: "chat",
          params: {
            message: content,
            attachments: attachments,
            project_id: currentProject?.project_id,
          },
        },
        project_id: currentProject?.project_id,
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
        promise = LogsService.getRecentLogs({
          device_id: Number(deviceId),
          limit: 20,
        })
      } else if (activeThreadId) {
        // LogsService.list is mapped to /api/log/list which takes thread_id
        promise = LogsService.getLogsByThread({
          thread_id: activeThreadId,
        })
      } else {
        promise = LogsService.getRecentLogs({
          device_id: Number(deviceId),
          limit: 50,
          project_id: currentProject?.project_id,
        })
      }

      promise
        .then((res: any) => {
          if (res.code >= 0 && Array.isArray(res.data)) {
            const logs = res.data
            const formatted = logs.map((log: any) => ({
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
        .catch((err: any) => {
          console.error("Failed to fetch history", err)
        })
    }
  }, [
    deviceId,
    setMessages,
    currentProject?.project_id,
    isProjectInitialized,
    highlight,
    activeThreadId,
  ])

  // Device Status
  const { data: devices } = useQuery({
    queryKey: ["evoloop", "devices"],
    queryFn: async () => {
      const res = await DevicesService.getDevices()
      if (res.code >= 0 && Array.isArray(res.data)) {
        return res.data
      }
      // If data is an object with list property, common in cloud APIs
      if (res.code >= 0 && (res.data as any)?.list) {
        return (res.data as any).list
      }
      return []
    },
    refetchInterval: 5000,
  })

  // Ensure devices is an array before calling find
  const devicesList = Array.isArray(devices) ? devices : []
  const currentDevice = devicesList.find(
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



  // Display all messages from the device in Local Chat.
  // Filtering by project_id is often unreliable due to desktop/cloud ID differences.
  const displayMessages = messages

  const handleHITLResponse = async (threadId: string, response: string, commandId?: number) => {
    try {
      await CommandService.sendCommand({
        device_id: Number(deviceId),
        content: {
          command_type: "hitl_response",
          params: {
            content: { response: response },
            thread_id: threadId,
            command_id: commandId
          }
        },
        project_id: currentProject?.project_id,
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
        activeThreadId={activeThreadId}
        onThreadSelect={setActiveThreadId}
        onClear={clearMessages}
      />

      <MessageList
        messages={displayMessages}
        isProjectInitialized={isProjectInitialized}
        isDeviceOnline={isDeviceOnline}
        highlight={highlight}
        onHITLResponse={handleHITLResponse}
        onStarterClick={handleSend}
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
