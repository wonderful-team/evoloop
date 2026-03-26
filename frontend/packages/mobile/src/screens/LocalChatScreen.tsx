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

  const { currentProject, isProjectInitialized } = useMobileStore()
  
  const {
    isConnected,
    isLocal,
    unifiedMessages,
    clearMessages,
    addMessage,
    setMessages,
    sendCommand,
  } = useEvoLoopWebSocket(Number(deviceId))

  const handleSend = async (content: string, attachments: any[] = []) => {
    addMessage({
      type: "user",
      content: content,
      project_id: currentProject?.project_id,
      timestamp: Date.now(),
    })

    const payload = {
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
      thread_id: activeThreadId,
    }

    const sentViaWs = sendCommand(payload as any)
    if (sentViaWs) {
      console.log("[Chat] Sent via WebSocket")
      return
    }

    try {
      await CommandService.sendCommand(payload)
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
      setTimeout(() => {
        handleSend(searchParams.initialMessage)
      }, 500)
    }
  }, [searchParams.initialMessage])

  // Fetch history
  useEffect(() => {
    if (deviceId && isProjectInitialized) {
      if (activeThreadId === "") {
        setMessages([])
        return
      }

      if (highlight) {
        LogsService.getRecentLogs({
          device_id: Number(deviceId),
          limit: 20,
          exclude_types: "error",
        }).then((res: any) => {
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
            setMessages(formatted as any)
          }
        }).catch(console.error)
        return
      }

      const promise = activeThreadId
        ? LogsService.getLogsByThread({
          thread_id: activeThreadId,
          exclude_types: "error"
        })
        : LogsService.getRecentLogs({
          device_id: Number(deviceId),
          limit: 50,
          project_id: currentProject?.project_id,
          exclude_types: "error"
        })

      promise
        .then((res: any) => {
          if (res.code >= 0 && Array.isArray(res.data)) {
            const logs = res.data
            const formatted = logs.map((log: any) => {
              let role = undefined
              if (log.type === "user") role = "user"
              if (["model", "assistant", "output", "answer"].includes(log.type)) role = "assistant"

              return {
                type: log.type || "info",
                role: role,
                content: log.content,
                thread_id: log.thread_id,
                project_id: log.project_id,
                log_id: log.log_id,
                timestamp: log.create_time ? log.create_time * 1000 : Date.now(),
              }
            })
            setMessages(activeThreadId ? formatted : formatted.reverse())
          }
        })
        .catch((err: any) => {
          console.error("Failed to fetch logs", err)
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
      if (res.code >= 0 && (res.data as any)?.list) {
        return (res.data as any).list
      }
      return []
    },
    refetchInterval: 10000,
    refetchOnWindowFocus: false,
  })

  const devicesList = Array.isArray(devices) ? devices : []
  const currentDevice = devicesList.find(
    (d: any) => d.device_id === Number(deviceId),
  )
  const isDeviceOnline = currentDevice?.status === 1

  let statusText = t("chat.local.connecting")
  let statusColor = "bg-yellow-500"
  let statusShadow = ""

  if (isConnected) {
    if (isLocal) {
        statusText = "Direct P2P"
        statusColor = "bg-blue-500"
        statusShadow = "shadow-[0_0_8px_rgba(59,130,246,0.5)]"
    } else if (isDeviceOnline) {
      statusText = t("chat.local.agentOnline")
      statusColor = "bg-green-500"
      statusShadow = "shadow-[0_0_8px_rgba(34,197,94,0.5)]"
    } else {
      statusText = t("chat.local.agentOffline")
      statusColor = "bg-red-500/80"
      statusShadow = ""
    }
  } else {
    statusText = t("chat.local.connectingServer")
    statusColor = "bg-red-500"
  }

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
        thread_id: threadId,
      })
      toast.success(t("hitl.responseSent"))
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
        onClear={() => {
          clearMessages()
        }}
      />

      <MessageList
        messages={unifiedMessages as any}
        isProjectInitialized={isProjectInitialized}
        isDeviceOnline={isDeviceOnline}
        highlight={highlight}
        onHITLResponse={handleHITLResponse}
        onStarterClick={handleSend}
        showStarters={unifiedMessages.length === 0}
      />

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
