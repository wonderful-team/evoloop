
import { useState, useEffect, useRef } from "react"
import { ChevronDown, ChevronRight, Cpu, Terminal, AlertTriangle, Loader2 } from "lucide-react"
import { LogMessage } from "@/hooks/useEvoLoopWebSocket"

interface MessageListProps {
    messages: LogMessage[]
    isProjectInitialized: boolean
    isDeviceOnline: boolean
    highlight: number | null
}

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

export function MessageList({ messages, isProjectInitialized, isDeviceOnline, highlight }: MessageListProps) {
    const scrollRef = useRef<HTMLDivElement>(null)

    // Auto-scroll
    useEffect(() => {
        if (scrollRef.current && !highlight) {
            scrollRef.current.scrollTop = scrollRef.current.scrollHeight
        }
    }, [messages, highlight])

    // Highlight logic should be handled by parent or here? 
    // In ChatScreen, it did setMessages then scroll.
    // Here we just render. The parent effect for scrolling to highlight might invoke refs?
    // Actually, let's keep the highlight scroll inside here if possible, or assume parent handles messages order.
    // But `scrollIntoView` needs DOM access.

    useEffect(() => {
        if (highlight) {
            setTimeout(() => {
                const element = document.getElementById(`log-${highlight}`);
                if (element) {
                    element.scrollIntoView({ behavior: 'smooth', block: 'center' });
                    element.classList.add('bg-primary/20');
                    setTimeout(() => element.classList.remove('bg-primary/20'), 2000);
                }
            }, 500);
        }
    }, [highlight, messages.length]) // Trigger when messages load

    return (
        <div className="flex-1 overflow-y-auto p-4 scroll-smooth" ref={scrollRef}>
            {!isProjectInitialized ? (
                <div className="h-full flex flex-col items-center justify-center p-8 text-center space-y-4">
                    <Loader2 className="w-8 h-8 animate-spin text-muted-foreground" />
                    <p className="text-sm text-muted-foreground">Initializing...</p>
                </div>
            ) : messages.length === 0 ? (
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
            ) : (
                messages.map((msg, i) => (
                    <div id={msg.log_id ? `log-${msg.log_id}` : undefined} key={i}>
                        <LogItem msg={msg} />
                    </div>
                ))
            )}
        </div>
    )
}
