
import { useState, useEffect } from "react"
import { Mic, Paperclip, Send, Loader2, Camera } from "lucide-react"
import { Button } from "@/components/ui/button"
import { toast } from "sonner"
import { useVoice } from "@/hooks/useVoice"
import { EvoLoopApi } from "@/client/evoloopClient"

interface ChatInputProps {
    isConnected: boolean
    isDeviceOnline: boolean
    onSend: (content: string) => Promise<void>
    className?: string
    innerClassName?: string
    placeholder?: string
}

export function ChatInput({ isConnected, isDeviceOnline, onSend, className, innerClassName, placeholder }: ChatInputProps) {
    const [input, setInput] = useState("")
    const [sending, setSending] = useState(false)
    const [isUploading, setIsUploading] = useState(false)

    // Native Plugin Hook
    const { isListening, transcript, startListening, stopListening } = useVoice({ language: 'zh-CN' })

    // Sync transcript to input
    useEffect(() => {
        if (transcript) {
            setInput(transcript)
        }
    }, [transcript])

    const toggleVoiceInput = async () => {
        if (isListening) {
            await stopListening()
        } else {
            await startListening()
        }
    }

    const handleSendAction = async () => {
        if (!input.trim()) return
        const content = input.trim()
        setSending(true)
        setInput("") // Clear immediately

        try {
            await onSend(content)
        } finally {
            setSending(false)
        }
    }

    const isInputDisabled = sending || !isConnected || !isDeviceOnline

    return (
        <div className={className || "bg-background border-t p-3 shrink-0 pb-[max(env(safe-area-inset-bottom),0.75rem)] sticky bottom-0 z-20"}>
            <form
                onSubmit={(e) => { e.preventDefault(); handleSendAction(); }}
                className={innerClassName || `flex flex-col gap-2 bg-muted/50 p-3 rounded-3xl border border-transparent focus-within:border-primary/50 focus-within:bg-background transition-all ${isListening ? 'ring-2 ring-red-500/50 bg-red-50/50' : ''} ${isInputDisabled ? 'opacity-50 pointer-events-none' : ''}`}
            >
                {/* Row 1: Text Input */}
                <div className="w-full">
                    <textarea
                        value={input}
                        onChange={e => setInput(e.target.value)}
                        placeholder={
                            placeholder || (
                                !isConnected ? "Connecting to server..." :
                                    !isDeviceOnline ? "Device is offline" :
                                        isListening ? "Listening..." : "Message agent..."
                            )
                        }
                        disabled={isInputDisabled}
                        className="w-full bg-transparent border-none focus:ring-0 p-1 text-base placeholder:text-muted-foreground/70 resize-none min-h-[40px] max-h-[120px] focus-visible:outline-none"
                        rows={1}
                        onInput={(e) => {
                            const target = e.target as HTMLTextAreaElement;
                            target.style.height = 'auto';
                            target.style.height = `${Math.min(target.scrollHeight, 120)}px`;
                        }}
                        onKeyDown={(e) => {
                            if (e.key === 'Enter' && !e.shiftKey) {
                                e.preventDefault()
                                handleSendAction()
                            }
                        }}
                    />
                    <input
                        type="file"
                        id="mobile-file-upload"
                        className="hidden"
                        onChange={async (e) => {
                            const file = e.target.files?.[0]
                            if (!file) return

                            setIsUploading(true)
                            try {
                                const url = await EvoLoopApi.uploadFile(file)
                                setInput(prev => prev + (prev ? "\n" : "") + `[File: ${url}]`)
                                toast.success("File uploaded")
                            } catch (error) {
                                toast.error("Upload failed")
                                console.error(error)
                            } finally {
                                setIsUploading(false)
                                e.target.value = ''
                            }
                        }}
                    />
                </div>

                {/* Row 2: Actions & Send */}
                <div className="flex justify-between items-center w-full">
                    {/* Left: Tools */}
                    <div className="flex gap-2">
                        <Button
                            type="button"
                            variant="ghost"
                            size="icon"
                            disabled={isInputDisabled}
                            className={`rounded-full w-9 h-9 transition-colors ${isListening ? 'text-red-500 hover:text-red-600 hover:bg-red-100' : 'text-muted-foreground hover:bg-background hover:text-primary'}`}
                            onClick={toggleVoiceInput}
                        >
                            <Mic className={`w-5 h-5 ${isListening ? 'animate-pulse' : ''}`} />
                        </Button>

                        <Button
                            type="button"
                            variant="ghost"
                            size="icon"
                            disabled={isInputDisabled || isUploading}
                            className="rounded-full w-9 h-9 text-muted-foreground hover:bg-background hover:text-primary"
                            onClick={() => document.getElementById('mobile-camera-upload')?.click()}
                        >
                            <Camera className="w-5 h-5" />
                        </Button>

                        <Button
                            type="button"
                            variant="ghost"
                            size="icon"
                            disabled={isInputDisabled || isUploading}
                            className="rounded-full w-9 h-9 text-muted-foreground hover:bg-background hover:text-primary"
                            onClick={() => document.getElementById('mobile-file-upload')?.click()}
                        >
                            {isUploading ? <Loader2 className="w-5 h-5 animate-spin" /> : <Paperclip className="w-5 h-5" />}
                        </Button>
                    </div>

                    <input
                        type="file"
                        id="mobile-camera-upload"
                        className="hidden"
                        accept="image/*"
                        capture="environment"
                        onChange={async (e) => {
                            const file = e.target.files?.[0]
                            if (!file) return
                            setIsUploading(true)
                            try {
                                const url = await EvoLoopApi.uploadFile(file)
                                setInput(prev => prev + (prev ? "\n" : "") + `[Image: ${url}]`)
                                toast.success("Image uploaded")
                            } catch (error) {
                                toast.error("Upload failed")
                            } finally {
                                setIsUploading(false)
                                e.target.value = ''
                            }
                        }}
                    />

                    {/* Right: Send */}
                    <Button
                        type="submit"
                        disabled={isInputDisabled || (!input.trim() && !isListening)}
                        size="icon"
                        className="rounded-full w-9 h-9 shadow-sm"
                    >
                        <Send className="w-4 h-4" />
                    </Button>
                </div>
            </form>
        </div>
    )
}
