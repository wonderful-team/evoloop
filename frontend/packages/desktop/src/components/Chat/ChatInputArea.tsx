import { BookOpen, Loader2, Paperclip, Send, Square } from "lucide-react"
import { memo, useState, useRef, forwardRef, useImperativeHandle } from "react"
import { useTranslation } from "react-i18next"
import { toast } from "sonner"
import { FilesService } from "@/client/sdk.gen"
import { SkillLibraryDialog } from "@/components/Learning/SkillLibraryDialog"
import { Button } from "@evoloop/shared/components/ui/button"
import { type Attachment, AttachmentPreview } from "./AttachmentPreview"
import { ReferencePicker, type ReferenceItem } from "./ReferencePicker"
import { RecordingButton } from "./RecordingButton"

interface ChatInputAreaProps {
  onSend: (text: string, attachments?: any[]) => void
  onStop: () => void
  isAgentWorking: boolean
  isSending: boolean
  isStopPending: boolean
  currentProject: { id?: number; name: string } | null | undefined
  activeThreadId?: string
  disabled?: boolean
  isGlobalMode?: boolean
}

export interface ChatInputAreaHandle {
  addReference: (item: ReferenceItem) => void
  setInput: (text: string) => void
}

export const ChatInputArea = memo(
  forwardRef<ChatInputAreaHandle, ChatInputAreaProps>((
    {
      onSend,
      onStop,
      isAgentWorking,
      isSending,
      isStopPending,
      currentProject,
      activeThreadId,
      disabled,
      isGlobalMode,
    }, ref) => {
    const { t } = useTranslation()
    const [inputValue, setInputValue] = useState("")
    const [isUploading, setIsUploading] = useState(false)
    const [attachments, setAttachments] = useState<Attachment[]>([])

    const [showPicker, setShowPicker] = useState(false)
    const textareaRef = useRef<HTMLTextAreaElement>(null)

    // History state
    const [history, setHistory] = useState<string[]>([])
    const [historyIndex, setHistoryIndex] = useState(-1) // -1: New Input, 0: Most recent history

    const handleSend = () => {
      if ((!inputValue.trim() && attachments.length === 0) || isSending) return

      // Pass raw input and attachments directly to store/parent
      // The store handles the optimistic display formatting and API payload construction
      onSend(inputValue, attachments)

      // Add to history (Newest first)
      if (inputValue.trim()) {
        setHistory(prev => [inputValue, ...prev])
      }
      setHistoryIndex(-1)

      // Clear state
      setInputValue("")
      setAttachments([])
    }

    const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
      if (e.key === "@") {
        setShowPicker(true)
      }

      if (e.key === "Enter" && !e.shiftKey) {
        if (showPicker) {
          e.preventDefault()
          handleSend()
        } else {
          e.preventDefault()
          handleSend()
        }
      }

      // History Traversal (Up/Down)
      // Only trigger if input is empty OR we are currently traversing history
      // This prevents interrupting multiline editing
      if ((inputValue === "" || historyIndex !== -1) && !e.shiftKey) {
        if (e.key === "ArrowUp") {
          e.preventDefault()
          const nextIndex = historyIndex + 1
          if (nextIndex < history.length) {
            setHistoryIndex(nextIndex)
            setInputValue(history[nextIndex])
            // Move cursor to end?
            setTimeout(() => {
              if (textareaRef.current) {
                textareaRef.current.selectionStart = textareaRef.current.value.length
                textareaRef.current.selectionEnd = textareaRef.current.value.length
              }
            }, 0)
          }
        } else if (e.key === "ArrowDown") {
          e.preventDefault()
          const nextIndex = historyIndex - 1
          if (nextIndex >= 0) {
            setHistoryIndex(nextIndex)
            setInputValue(history[nextIndex])
          } else {
            setHistoryIndex(-1)
            setInputValue("")
          }
        }
      }
    }

    const handleUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
      const file = e.target.files?.[0]
      if (!file) return

      setIsUploading(true)
      try {
        if (!currentProject || !currentProject.id) {
          throw new Error("No project context")
        }
        const res: any = await FilesService.uploadFile({
          projectId: currentProject.id,
          formData: { file },
        })
        const url = res.url

        // Infer type
        const isImage = file.type.startsWith("image/")
        const newAtt: Attachment = {
          id: crypto.randomUUID(),
          url: url,
          name: file.name,
          type: isImage ? "image" : "file",
        }

        setAttachments((prev) => [...prev, newAtt])
        toast.success(t("chat.interface.uploadSuccess"))
      } catch (error: any) {
        toast.error(
          t("chat.interface.uploadError") +
          (error.message ? `: ${error.message}` : ""),
        )
        console.error(error)
      } finally {
        setIsUploading(false)
        e.target.value = ""
      }
    }

    const handleSelectReference = (item: ReferenceItem) => {
      // Insert text at cursor
      const textarea = textareaRef.current
      if (textarea) {
        const start = textarea.selectionStart
        const end = textarea.selectionEnd
        const text = inputValue
        const before = text.substring(0, start)
        const after = text.substring(end)

        // Only add space if needed
        const prefix = before.endsWith(" ") ? "" : " "
        const suffix = after.startsWith(" ") ? "" : " "

        const newText = before + prefix + `@${item.name}` + suffix + after
        setInputValue(newText)

        // Add to attachments
        const newAtt: Attachment = {
          id: crypto.randomUUID(),
          url: item.id,
          name: item.name,
          type: item.type === 'file' ? 'file' : 'reference',
        }
        if (item.type === 'message') {
          newAtt.type = 'message'
        }

        setAttachments(prev => {
          // Avoid duplicates
          if (prev.some(a => a.url === newAtt.url)) return prev
          return [...prev, newAtt]
        })

        // Restore focus
        setTimeout(() => {
          textarea.focus()
          // Update cursor position ???
        }, 0)
      }
      setShowPicker(false)
    }

    useImperativeHandle(ref, () => ({
      addReference: (item: ReferenceItem) => {
        handleSelectReference(item)
      },
      setInput: (text: string) => {
        setInputValue(text)
      }
    }))

    return (
      <div
        className="shrink-0 p-4 pt-2 bg-background/95 backdrop-blur supports-[backdrop-filter]:bg-background/60"
        data-tour="chat-input"
      >
        <div className="w-full max-w-4xl mx-auto relative">
          {/* Reference Picker Popover - Hidden in global mode */}
          {showPicker && currentProject && !isGlobalMode && (
            <div className="absolute bottom-full left-0 mb-2 z-50">
              <ReferencePicker
                projectId={currentProject.id!}
                onSelect={handleSelectReference}
                onClose={() => setShowPicker(false)}
              />
              {/* Click outside backdrop */}
              <div
                className="fixed inset-0 z-40"
                onClick={() => setShowPicker(false)}
              />
            </div>
          )}

          <div className="bg-background rounded-2xl shadow-sm border border-input transition-all focus-within:ring-2 focus-within:ring-ring ring-offset-2 overflow-hidden relative z-50">
            {/* Top: Attachment Preview */}
            <AttachmentPreview
              attachments={attachments}
              onRemove={(id) =>
                setAttachments((prev) => prev.filter((a) => a.id !== id))
              }
            />

            {/* Middle: Text Area */}
            <div className="px-3 py-2">
              <textarea
                ref={textareaRef}
                value={inputValue}
                onChange={(e) => setInputValue(e.target.value)}
                onKeyDown={handleKeyDown}
                placeholder={
                  disabled
                    ? t("chat.interface.inputDisabled", "Please respond to the active request above...")
                    : isGlobalMode
                      ? t("chat.interface.askGlobal", "询问任何问题...")
                      : currentProject
                        ? t("chat.interface.askProject", {
                          project: currentProject.name,
                        })
                        : t("chat.interface.selectProject")
                }
                disabled={(!currentProject && !isGlobalMode) || disabled}
                className="flex w-full bg-transparent border-none focus:ring-0 text-sm placeholder:text-muted-foreground resize-none focus-visible:outline-none disabled:cursor-not-allowed disabled:opacity-50 min-h-[50px] max-h-[300px]"
                rows={1}
                style={{ height: "auto", minHeight: "50px" }}
                onInput={(e) => {
                  // Auto-grow hack
                  const target = e.target as HTMLTextAreaElement
                  target.style.height = "auto"
                  target.style.height = `${Math.min(target.scrollHeight, 500)}px`
                }}
              />
            </div>

            {/* Bottom: Toolbar */}
            <div className="relative flex items-center justify-between border-t border-border/40 bg-muted/20 p-2">
              {/* Hint Text (Centered) */}
              <div className="pointer-events-none absolute left-1/2 top-1/2 -translate-x-1/2 -translate-y-1/2 select-none text-[10px] text-muted-foreground/50 whitespace-nowrap hidden sm:block">
                {t("chat.interface.inputHint")}
              </div>

              {/* Left Group: Tools */}
              <div className="flex items-center gap-1">
                {activeThreadId && !isGlobalMode && (
                  <>
                    <SkillLibraryDialog
                      threadId={activeThreadId}
                      projectId={currentProject?.id}
                      trigger={
                        <Button
                          variant="ghost"
                          size="icon"
                          className="h-8 w-8 text-muted-foreground hover:text-foreground"
                          title={t("learning.skillLibrary")}
                        >
                          <BookOpen size={16} />
                        </Button>
                      }
                    />
                    <div className="h-8 flex items-center justify-center">
                      <RecordingButton
                        threadId={activeThreadId}
                        enabled={!!currentProject}
                      />
                    </div>
                  </>
                )}
              </div>

              {/* Right Group: Action */}
              <div className="flex items-center gap-2">
                {/* File upload hidden in global mode */}
                {!isGlobalMode && (
                  <>
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
                      onClick={() =>
                        document.getElementById("chat-file-upload")?.click()
                      }
                      disabled={isUploading || !currentProject}
                      title={t("chat.interface.uploadFile")}
                    >
                      {isUploading ? (
                        <Loader2 size={16} className="animate-spin" />
                      ) : (
                        <Paperclip size={16} />
                      )}
                    </Button>

                    <div className="w-px h-6 bg-border mx-1" />
                  </>
                )}

                <Button
                  onClick={() => (isAgentWorking ? onStop() : handleSend())}
                  disabled={
                    (!inputValue.trim() &&
                      attachments.length === 0 &&
                      !isAgentWorking) ||
                    isSending ||
                    (!currentProject && !isGlobalMode) ||
                    isUploading
                  }
                  size="sm"
                  className={`h-8 px-3 rounded-lg transition-all ${isAgentWorking ? "bg-red-500 hover:bg-red-600 text-white shadow-red-500/20 shadow-lg animate-pulse" : "shadow-primary/20 shadow-md"}`}
                >
                  {isAgentWorking || isStopPending ? (
                    <span className="flex items-center gap-2">
                      {isStopPending ? (
                        <Loader2 size={14} className="animate-spin" />
                      ) : (
                        <Square size={14} fill="currentColor" />
                      )}
                      <span className="text-xs font-medium">
                        {t("common.stop", "Stop")}
                      </span>
                    </span>
                  ) : (
                    <span className="flex items-center gap-2">
                      <Send size={14} />
                      <span className="text-xs font-bold">
                        {t("common.send", "Send")}
                      </span>
                    </span>
                  )}
                </Button>
              </div>
            </div>
          </div>
        </div>
      </div>
    )
  })
)

ChatInputArea.displayName = "ChatInputArea"
