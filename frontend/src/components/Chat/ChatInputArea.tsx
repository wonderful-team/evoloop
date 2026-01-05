
import { useState } from "react"
import { useTranslation } from "react-i18next"
import { toast } from "sonner"
import { Button } from "../ui/button"
import { Send, Loader2, Paperclip, Square } from "lucide-react"
import { EvoLoopApi } from "@/client/evoloopClient"

interface ChatInputAreaProps {
    onSend: (text: string) => void
    onStop: () => void
    isAgentWorking: boolean
    isSending: boolean
    isStopPending: boolean
    currentProject: { name: string } | null | undefined
}

export function ChatInputArea({
    onSend,
    onStop,
    isAgentWorking,
    isSending,
    isStopPending,
    currentProject
}: ChatInputAreaProps) {
    const { t } = useTranslation()
    const [inputValue, setInputValue] = useState("")
    const [isUploading, setIsUploading] = useState(false)

    const handleSend = () => {
        if (!inputValue.trim() || isSending) return
        onSend(inputValue)
        setInputValue("")
    }

    return (
        <div className="shrink-0 p-4 pt-2 bg-background/95 backdrop-blur supports-[backdrop-filter]:bg-background/60">
            <div className="w-full max-w-3xl mx-auto">
                <div className="bg-background rounded-2xl shadow-sm border border-input p-2 flex items-end gap-2 transition-all focus-within:ring-2 focus-within:ring-ring ring-offset-2">
                    <Button variant="ghost" size="icon" className="shrink-0 mb-1 h-8 w-8 rounded-full" onClick={() => document.getElementById('chat-file-upload')?.click()} disabled={isUploading}>
                        {isUploading ? <Loader2 size={18} className="animate-spin text-muted-foreground" /> : <Paperclip size={18} className="text-muted-foreground" />}
                    </Button>
                    <input
                        type="file"
                        id="chat-file-upload"
                        className="hidden"
                        onChange={async (e) => {
                            const file = e.target.files?.[0]
                            if (!file) return

                            setIsUploading(true)
                            try {
                                const url = await EvoLoopApi.uploadFile(file)
                                setInputValue(prev => prev + (prev ? "\n" : "") + `[File: ${url}]`)
                                toast.success(t('chat.interface.uploadSuccess'))
                            } catch (error) {
                                toast.error(t('chat.interface.uploadError'))
                                console.error(error)
                            } finally {
                                setIsUploading(false)
                                // Reset input
                                e.target.value = ''
                            }
                        }}
                    />
                    <textarea
                        value={inputValue}
                        onChange={(e: React.ChangeEvent<HTMLTextAreaElement>) => setInputValue(e.target.value)}
                        onKeyDown={(e: React.KeyboardEvent<HTMLTextAreaElement>) => {
                            if (e.key === 'Enter' && !e.shiftKey) {
                                e.preventDefault()
                                handleSend()
                            }
                        }}
                        placeholder={currentProject ? t('chat.interface.askProject', { project: currentProject.name }) : t('chat.interface.selectProject')}
                        disabled={!currentProject}
                        className="flex min-h-[44px] w-full bg-transparent border-none focus:ring-0 px-2 py-2.5 text-sm placeholder:text-muted-foreground resize-y focus-visible:outline-none disabled:cursor-not-allowed disabled:opacity-50 max-h-[300px]"
                        rows={1}
                    />
                    <Button
                        onClick={() => {
                            if (isAgentWorking) {
                                onStop()
                            } else {
                                handleSend()
                            }
                        }}
                        disabled={(!inputValue.trim() && !isAgentWorking) || isSending || !currentProject || isUploading}
                        size="icon"
                        className={`mb-0.5 h-9 w-9 rounded-xl shadow-sm transition-all ${isAgentWorking ? "bg-red-500 hover:bg-red-600 text-white animate-pulse" : ""}`}
                        title={isAgentWorking ? t('chat.interface.stop', "Stop Generating") : t('chat.interface.send', "Send Message")}
                    >
                        {isAgentWorking || isStopPending ? (
                            isStopPending ? <Loader2 size={16} className="animate-spin" /> : <Square size={16} fill="currentColor" />
                        ) : (
                            <Send size={16} />
                        )}
                    </Button>
                </div>
            </div>
        </div>
    )
}
