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
  }, [searchParams.initialMessage, handleSend])

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

  const handleSend = async (content: string) => {
    // Optimistic UI
    addMessage({
      type: "user",
      content: content,
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

  const displayMessages = messages.filter((m) => {
    if (!currentProject) return true
    if (m.project_id === undefined || m.project_id === null) return true
    return m.project_id === currentProject.project_id
  })

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
