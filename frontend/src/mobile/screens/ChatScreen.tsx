import { useParams, useNavigate } from "@tanstack/react-router"
import { useEvoLoopWebSocket, LogMessage } from "@/hooks/useEvoLoopWebSocket"
import { useVoice } from "@/hooks/useVoice"
import { EvoLoopApi } from "@/client/evoloopClient"
import { useState, useRef, useEffect } from "react"
import { Send, Cpu, Terminal, AlertTriangle, ArrowLeft, ChevronDown, ChevronRight, Mic } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { toast } from "sonner"
import { useQuery } from "@tanstack/react-query"




function LogItem({ msg }: { msg: LogMessage }) {
    const [isOpen, setIsOpen] = useState(false);

    if (msg.type === 'user') {
        return (
            <div className="flex justify-end mb-4 animate-in slide-in-from-right-2 fade-in duration-300">
                <div className="bg-primary text-primary-foreground px-4 py-2 rounded-2xl rounded-tr-sm max-w-[85%] text-sm shadow-sm">
                    {msg.content}
                </div>
            </div>
        )
    }

    if (msg.type === 'thought') {
        return (
            <div className="mb-3 animate-in fade-in duration-300">
                <button
                    onClick={() => setIsOpen(!isOpen)}
                    className="flex items-center gap-2 text-xs font-medium text-muted-foreground hover:text-foreground transition-colors w-full mb-1"
                >
                    {isOpen ? <ChevronDown className="w-3 h-3" /> : <ChevronRight className="w-3 h-3" />}
                    <Cpu className="w-3 h-3" />
                    Agent Thought Process
                </button>
                {isOpen && (
                    <div className="ml-2 pl-3 border-l-2 border-primary/20 text-xs font-mono text-muted-foreground bg-muted/30 p-2 rounded-r-md">
                        {msg.content}
                    </div>
                )}
            </div>
        )
    }

    if (msg.type === 'tool') {
        return (
            <div className="mb-3 ml-2 pl-3 border-l-2 border-muted-foreground/30 animate-in fade-in duration-300">
                <div className="flex items-center gap-2 text-xs text-muted-foreground mb-1">
                    <Terminal className="w-3 h-3" />
                    <span>Tool Execution</span>
                </div>
                <div className="bg-muted rounded-md p-2 text-xs font-mono text-muted-foreground overflow-x-auto">
                    {msg.content}
                </div>
            </div>
        )
    }

    if (msg.type === 'error') {
        return (
            <div className="flex gap-2 mb-3 p-3 bg-destructive/10 rounded-lg text-sm text-destructive border-l-4 border-destructive animate-in shake">
                <AlertTriangle className="w-4 h-4 mt-0.5 shrink-0" />
                <div className="break-words">{msg.content}</div>
            </div>
        )
    }

    // Default Output
    return (
        <div className="flex justify-start mb-4 animate-in slide-in-from-left-2 fade-in duration-300">
            <div className="bg-card border border-border text-card-foreground px-4 py-3 rounded-2xl rounded-tl-sm max-w-[85%] text-sm shadow-sm">
                <div className="whitespace-pre-wrap">{msg.content}</div>
            </div>
        </div>
    )
}

export function ChatScreen() {
    // manual route param
    const { deviceId } = useParams({ strict: false }) as any
    const navigate = useNavigate()
    const [input, setInput] = useState("")
    const [sending, setSending] = useState(false)

    const { isConnected, messages, clearMessages, addMessage } = useEvoLoopWebSocket(Number(deviceId))
    const scrollRef = useRef<HTMLDivElement>(null)

    // Fetch device status
    const { data: devices } = useQuery({
        queryKey: ['evoloop', 'devices'],
        queryFn: EvoLoopApi.getDeviceList,
        refetchInterval: 5000,
    })

    const currentDevice = devices?.find(d => d.device_id === Number(deviceId))
    const isDeviceOnline = currentDevice?.status === 1

    // Determine overall status text and color
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


    // Auto-scroll
    useEffect(() => {
        if (scrollRef.current) {
            scrollRef.current.scrollTop = scrollRef.current.scrollHeight
        }
    }, [messages])

    const handleSend = async () => {
        if (!input.trim()) return
        const content = input.trim()
        setSending(true)

        // Optimistic UI
        addMessage({
            type: 'user',
            content: content,
            timestamp: Date.now()
        })
        setInput("")

        try {
            await EvoLoopApi.sendCommand(Number(deviceId), content)
        } catch (e: any) {
            toast.error("Failed to send command: " + e.message)
            addMessage({
                type: 'error',
                content: "Failed to deliver message: " + e.message,
                timestamp: Date.now()
            })
        } finally {
            setSending(false)
        }
    }

    // Native Plugin Hook
    const { isListening, transcript, startListening, stopListening } = useVoice({ language: 'zh-CN' })

    // Sync transcript to input
    useEffect(() => {
        if (transcript) {
            // Append or replace? Usually append is better for chat.
            // But if it updates continuously, we need to be careful not to duplicate.
            // My useVoice sets transcript to the latest result.
            // If partial results are enabled, it might just be the full current phrase.
            // A simple approach is: when listening starts, clear input? Or append?
            // Let's assume transcript is the *current utterance*.
            // We want to append it to `input` only when it's final?
            // The current hook just sets `transcript`.
            // A common pattern: Display transcript in placeholder or separate view, then commit to input on stop?
            // Or just setInput(transcript).
            // Let's try: While listening, Input shows `transcript`.
            // If we want to append to existing text, we need to separate "previous text" and "current voice text".
            // For simplicity in this v1:
            // When voice starts, we might clear input or ignore previous?
            // Let's just setInput(transcript) for now, assuming voice is the primary input method when active.
            setInput(transcript)
        }
    }, [transcript])

    const toggleVoiceInput = async () => {
        if (isListening) {
            await stopListening()
        } else {
            // Check platform? The plugin handles permissions.
            await startListening()
        }
    }

    // Input disabled state: if sending OR device is offline (and we are not purely testing UI / not connected)
    // Actually, if device is offline, we definitely shouldn't send.
    // If not connected to WS, we also shouldn't send.
    const isInputDisabled = sending || !isConnected || !isDeviceOnline

    return (
        <div className="flex flex-col h-screen bg-background">
            {/* Header */}
            <div className="bg-background/80 backdrop-blur-md border-b px-4 py-3 flex items-center gap-3 sticky top-0 z-10 shrink-0">
                <Button variant="ghost" size="icon" className="-ml-2 hover:bg-muted" onClick={() => navigate({ to: '/devices' as any })}>
                    <ArrowLeft className="w-5 h-5" />
                </Button>
                <div className="flex-1">
                    <h1 className="font-semibold text-sm flex items-center gap-2">
                        {currentDevice?.device_name || `Device #${deviceId}`}
                    </h1>
                    <div className="flex items-center gap-1.5">
                        <span className={`w-2 h-2 rounded-full ${statusColor} ${statusShadow} transition-colors duration-300`} />
                        <span className="text-xs text-muted-foreground transition-all duration-300">{statusText}</span>
                    </div>
                </div>
                <Button variant="ghost" size="sm" className="text-muted-foreground text-xs h-8" onClick={clearMessages}>
                    Clear
                </Button>
            </div>

            {/* Chat Area */}
            <div className="flex-1 overflow-y-auto p-4 scroll-smooth" ref={scrollRef}>
                {messages.length === 0 && (
                    <div className="h-full flex flex-col items-center justify-center p-8 text-center space-y-4">
                        <div className={`w-16 h-16 rounded-full flex items-center justify-center transition-colors ${isDeviceOnline ? 'bg-muted' : 'bg-red-50'}`}>
                            {isDeviceOnline ? (
                                <Terminal className="w-8 h-8 text-muted-foreground" />
                            ) : (
                                <AlertTriangle className="w-8 h-8 text-red-300" />
                            )}
                        </div>
                        <div className="space-y-2">
                            <h3 className="font-semibold text-foreground">
                                {isDeviceOnline ? 'Ready to Connect' : 'Device Offline'}
                            </h3>
                            <p className="text-sm text-muted-foreground max-w-[200px]">
                                {isDeviceOnline
                                    ? 'Send instructions to control the remote agent.'
                                    : 'The remote device is currently not connected.'}
                            </p>
                        </div>
                    </div>
                )}
                {messages.map((msg, i) => (
                    <LogItem key={i} msg={msg} />
                ))}
            </div>

            {/* Input Area */}
            <div className="bg-background border-t p-3 shrink-0 pb-[max(env(safe-area-inset-bottom),0.75rem)] sticky bottom-0 z-20">
                <form
                    onSubmit={(e) => { e.preventDefault(); handleSend(); }}
                    className={`flex gap-2 items-end bg-muted/50 p-1.5 rounded-3xl border border-transparent focus-within:border-primary/50 focus-within:bg-background transition-all ${isListening ? 'ring-2 ring-red-500/50 bg-red-50/50' : ''} ${isInputDisabled ? 'opacity-50 pointer-events-none' : ''}`}
                >
                    {/* Voice Button - Hide or Disable if offline */}
                    <Button
                        type="button"
                        variant="ghost"
                        size="icon"
                        disabled={isInputDisabled}
                        className={`rounded-full w-10 h-10 shrink-0 mb-0.5 transition-colors ${isListening ? 'text-red-500 hover:text-red-600 hover:bg-red-100' : 'text-muted-foreground hover:bg-background hover:text-primary'}`}
                        onClick={toggleVoiceInput}
                    >
                        <Mic className={`w-5 h-5 ${isListening ? 'animate-pulse' : ''}`} />
                    </Button>
                    <Input
                        value={input}
                        onChange={e => setInput(e.target.value)}
                        placeholder={
                            !isConnected ? "Connecting to server..." :
                                !isDeviceOnline ? "Device is offline" :
                                    isListening ? "Listening..." : "Message agent..."
                        }
                        disabled={isInputDisabled}
                        className="border-0 shadow-none focus-visible:ring-0 bg-transparent min-h-[44px] px-2 py-3 placeholder:text-muted-foreground/70"
                    />
                    <Button
                        type="submit"
                        disabled={isInputDisabled || (!input.trim() && !isListening)}
                        size="icon"
                        className="rounded-full w-10 h-10 shrink-0 mb-0.5"
                    >
                        <Send className="w-4 h-4" />
                    </Button>
                </form>
            </div>
        </div>
    )
}
