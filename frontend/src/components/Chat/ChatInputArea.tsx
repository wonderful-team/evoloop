import { useState, memo } from "react"
import { useTranslation } from "react-i18next"
import { toast } from "sonner"
import { Button } from "../ui/button"
import { Send, Loader2, Paperclip, Square } from "lucide-react"
import { EvoLoopApi } from "@/client/evoloopClient"
import { RecordingButton } from "./RecordingButton"
import { SkillLibraryDialog } from "@/components/Learning/SkillLibraryDialog"
import { BookOpen } from "lucide-react"
import { Attachment, AttachmentPreview } from "./AttachmentPreview"

interface ChatInputAreaProps {
    onSend: (text: string) => void
    onStop: () => void
    isAgentWorking: boolean
    isSending: boolean
    isStopPending: boolean
    currentProject: { id?: number, name: string } | null | undefined
    activeThreadId?: string
}

export const ChatInputArea = memo(({
    onSend,
    onStop,
    isAgentWorking,
    isSending,
    isStopPending,
    currentProject,
    activeThreadId
}: ChatInputAreaProps) => {
    const { t } = useTranslation()
    const [inputValue, setInputValue] = useState("")
    const [isUploading, setIsUploading] = useState(false)
    const [attachments, setAttachments] = useState<Attachment[]>([])

    const handleSend = () => {
        if ((!inputValue.trim() && attachments.length === 0) || isSending) return

        // Build final message with attachments appended
        let finalMessage = inputValue
        if (attachments.length > 0) {
            const attachmentLinks = attachments.map(att => `[File: ${att.url}]`).join("\n")
            finalMessage = finalMessage ? `${finalMessage}\n${attachmentLinks}` : attachmentLinks
        }

        onSend(finalMessage)

        // Clear state
        setInputValue("")
        setAttachments([])
    }

    const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
        if (e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault()
            handleSend()
        }
    }

    const handleUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
        const file = e.target.files?.[0]
        if (!file) return

        setIsUploading(true)
        try {
            const url = await EvoLoopApi.uploadFile(file)

            // Infer type
            const isImage = file.type.startsWith('image/')
            const newAtt: Attachment = {
                id: crypto.randomUUID(),
                url: url,
                name: file.name,
                type: isImage ? 'image' : 'file'
            }

            setAttachments(prev => [...prev, newAtt])
            toast.success(t('chat.interface.uploadSuccess'))
        } catch (error) {
            toast.error(t('chat.interface.uploadError'))
            console.error(error)
        } finally {
            setIsUploading(false)
            e.target.value = ''
        }
    }

    return (
        <div className="shrink-0 p-4 pt-2 bg-background/95 backdrop-blur supports-[backdrop-filter]:bg-background/60">
            <div className="w-full max-w-4xl mx-auto">
                <div className="bg-background rounded-2xl shadow-sm border border-input transition-all focus-within:ring-2 focus-within:ring-ring ring-offset-2 overflow-hidden">

                    {/* Top: Attachment Preview */}
                    <AttachmentPreview
                        attachments={attachments}
                        onRemove={(id) => setAttachments(prev => prev.filter(a => a.id !== id))}
                    />

                    {/* Middle: Text Area */}
                    <div className="px-3 py-2">
                        <textarea
                            value={inputValue}
                            onChange={(e) => setInputValue(e.target.value)}
                            onKeyDown={handleKeyDown}
                            placeholder={currentProject ? t('chat.interface.askProject', { project: currentProject.name }) : t('chat.interface.selectProject')}
                            disabled={!currentProject}
                            className="flex w-full bg-transparent border-none focus:ring-0 text-sm placeholder:text-muted-foreground resize-none focus-visible:outline-none disabled:cursor-not-allowed disabled:opacity-50 min-h-[50px] max-h-[300px]"
                            rows={1}
                            style={{ height: 'auto', minHeight: '50px' }}
                            onInput={(e) => {
                                // Auto-grow hack
                                const target = e.target as HTMLTextAreaElement;
                                target.style.height = 'auto';
                                target.style.height = `${Math.min(target.scrollHeight, 300)}px`;
                            }}
                        />
                    </div>

                    {/* Bottom: Toolbar */}
                    <div className="flex justify-between items-center p-2 bg-muted/20 border-t border-border/40">
                        {/* Left Group: Tools */}
                        <div className="flex items-center gap-1">
                            {activeThreadId && (
                                <>
                                    <SkillLibraryDialog
                                        threadId={activeThreadId}
                                        projectId={currentProject?.id}
                                        trigger={
                                            <Button variant="ghost" size="icon" className="h-8 w-8 text-muted-foreground hover:text-foreground" title="Skill Library">
                                                <BookOpen size={16} />
                                            </Button>
                                        }
                                    />
                                    <div className="h-8 flex items-center justify-center">
                                        <RecordingButton threadId={activeThreadId} enabled={!!currentProject} />
                                    </div>
                                </>
                            )}
                        </div>

                        {/* Right Group: Action */}
                        <div className="flex items-center gap-2">
                            <input
                                type="file"
                                id="chat-file-upload"
                                className="hidden"
                                onChange={handleUpload}
                                disabled={!currentProject || isUploading}
                            />
                            <Button
                                variant="ghost"
                                size="icon"
                                className="h-8 w-8 text-muted-foreground hover:text-foreground"
                                onClick={() => document.getElementById('chat-file-upload')?.click()}
                                disabled={isUploading || !currentProject}
                                title="Upload File"
                            >
                                {isUploading ? <Loader2 size={16} className="animate-spin" /> : <Paperclip size={16} />}
                            </Button>

                            <div className="w-px h-6 bg-border mx-1" />

                            <Button
                                onClick={() => isAgentWorking ? onStop() : handleSend()}
                                disabled={((!inputValue.trim() && attachments.length === 0) && !isAgentWorking) || isSending || !currentProject || isUploading}
                                size="sm"
                                className={`h-8 px-3 rounded-lg transition-all ${isAgentWorking ? "bg-red-500 hover:bg-red-600 text-white shadow-red-500/20 shadow-lg animate-pulse" : "shadow-primary/20 shadow-md"}`}
                            >
                                {isAgentWorking || isStopPending ? (
                                    <span className="flex items-center gap-2">
                                        {isStopPending ? <Loader2 size={14} className="animate-spin" /> : <Square size={14} fill="currentColor" />}
                                        <span className="text-xs font-medium">{t('common.stop', 'Stop')}</span>
                                    </span>
                                ) : (
                                    <span className="flex items-center gap-2">
                                        <Send size={14} />
                                        <span className="text-xs font-bold">{t('common.send', 'Send')}</span>
                                    </span>
                                )}
                            </Button>
                        </div>
                    </div>
                </div>

                {/* Hint Text */}
                <div className="text-[10px] text-center mt-2 text-muted-foreground/60 select-none">
                    Enter to send, Shift + Enter for new line
                </div>
            </div>
        </div>
    )
})

ChatInputArea.displayName = "ChatInputArea"
