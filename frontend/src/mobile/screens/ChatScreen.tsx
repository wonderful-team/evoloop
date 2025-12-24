
import { useParams, useSearch } from "@tanstack/react-router"
import { useEvoLoopWebSocket } from "@/hooks/useEvoLoopWebSocket"
import { EvoLoopApi } from "@/client/evoloopClient"
import { useEffect, useRef } from "react"
import { toast } from "sonner"
import { useQuery } from "@tanstack/react-query"
import { useMobileStore } from "../stores/useMobileStore"
import { ChatHeader } from "../components/chat/ChatHeader"
import { MessageList } from "../components/chat/MessageList"
import { ChatInput } from "../components/chat/ChatInput"
import { ArrowDownCircle } from "lucide-react"
import { Button } from "@/components/ui/button"
import { useNavigate } from "@tanstack/react-router"

export function ChatScreen() {
    const { deviceId } = useParams({ strict: false }) as any
    const searchParams = useSearch({ strict: false }) as any
    const highlight = searchParams.highlight ? Number(searchParams.highlight) : null
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
    }, [searchParams.initialMessage])

    const { currentProject, isProjectInitialized } = useMobileStore()
    const { isConnected, messages, clearMessages, addMessage, setMessages } = useEvoLoopWebSocket(Number(deviceId))

    // Fetch history
    useEffect(() => {
        if (deviceId && isProjectInitialized) {
            let promise;
            if (highlight) {
                promise = EvoLoopApi.getContextLogs(Number(deviceId), highlight);
            } else {
                promise = EvoLoopApi.getRecentLogs(Number(deviceId), 50, currentProject?.project_id);
            }

            promise.then(logs => {
                if (Array.isArray(logs)) {
                    const formatted = logs.map(log => ({
                        type: log.type || 'info',
                        content: log.content,
                        thread_id: log.thread_id,
                        project_id: log.project_id,
                        log_id: log.log_id,
                        timestamp: log.create_time ? log.create_time * 1000 : Date.now()
                    }));

                    if (highlight) {
                        // Context logs are usually ASC, so no reverse needed if backend returns ASC
                        setMessages(formatted as any);
                    } else {
                        // recent logs are DESC, so reverse for chat
                        setMessages(formatted.reverse() as any);
                    }
                }
            }).catch(err => {
                console.error("Failed to fetch history", err)
            })
        }
    }, [deviceId, setMessages, currentProject?.project_id, isProjectInitialized, highlight])

    // Device Status
    const { data: devices } = useQuery({
        queryKey: ['evoloop', 'devices'],
        queryFn: EvoLoopApi.getDeviceList,
        refetchInterval: 5000,
    })

    const currentDevice = devices?.find(d => d.device_id === Number(deviceId))
    const isDeviceOnline = currentDevice?.status === 1

    let statusText = 'Connecting...'
    let statusColor = 'bg-yellow-500'
    let statusShadow = ''

    if (isConnected) {
        if (isDeviceOnline) {
            statusText = 'Agent Online'
            statusColor = 'bg-green-500'
            statusShadow = 'shadow-[0_0_8px_rgba(34,197,94,0.5)]'
        } else {
            statusText = 'Device Offline'
            statusColor = 'bg-gray-400'
        }
    } else {
        statusText = 'Connecting to Server...'
        statusColor = 'bg-red-500'
    }

    const handleSend = async (content: string) => {
        // Optimistic UI
        addMessage({
            type: 'user',
            content: content,
            project_id: currentProject?.project_id,
            timestamp: Date.now()
        })

        try {
            await EvoLoopApi.sendCommand(Number(deviceId), content, currentProject?.project_id)
        } catch (e: any) {
            toast.error("Failed to send command: " + e.message)
            addMessage({
                type: 'error',
                content: "Failed to deliver message: " + e.message,
                timestamp: Date.now()
            })
        }
    }

    const displayMessages = messages.filter(m => {
        if (!currentProject) return true;
        if (m.project_id === undefined || m.project_id === null) return true;
        return m.project_id === currentProject.project_id;
    });

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
                        Back to Live
                    </Button>
                </div>
            )}

            <ChatInput
                isConnected={isConnected}
                isDeviceOnline={isDeviceOnline}
                onSend={handleSend}
            />
        </div>
    )
}
