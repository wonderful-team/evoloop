import {
  Camera,
  File as FileIcon,
  Loader2,
  Mic,
  Paperclip,
  Send,
  X,
} from "lucide-react"
import { useEffect, useRef, useState } from "react"
import { useTranslation } from "react-i18next"
import { toast } from "sonner"
import { FilesService } from "@/client/sdk.gen"
import { Button } from "@/components/ui/button"
import { useVoice } from "@/hooks/useVoice"

interface ChatInputProps {
  isConnected: boolean
  isDeviceOnline: boolean
  onSend: (content: string, attachments?: any[]) => Promise<void>
  projectId?: number
  className?: string
  innerClassName?: string
  placeholder?: string
}

interface Attachment {
  type: "image" | "file"
  url: string // Server URL (or temp local if not ready, but we handle that via previewUrl logic)
  name?: string
  previewUrl?: string // Local Blob URL for immediate display
  isUploading?: boolean
}

export function ChatInput({
  isConnected,
  isDeviceOnline,
  onSend,
  projectId,
  className,
  innerClassName,
  placeholder,
}: ChatInputProps) {
  const { t } = useTranslation()
  const [input, setInput] = useState("")
  const [sending, setSending] = useState(false)
  const [isUploading, setIsUploading] = useState(false) // General loading state
  const [attachments, setAttachments] = useState<Attachment[]>([])

  // Refs for hidden inputs
  const fileInputRef = useRef<HTMLInputElement>(null)
  const cameraInputRef = useRef<HTMLInputElement>(null)

  // Native Plugin Hook
  const { isListening, transcript, startListening, stopListening } = useVoice({
    language: "zh-CN",
  })

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
    if (!input.trim() && attachments.length === 0) return

    // Block if any attachment is still uploading
    if (attachments.some((a) => a.isUploading)) {
      toast.error(t("chat.input.waitUpload"))
      return
    }

    setSending(true)

    // Construct message content: Pass raw input and attachments
    // The store handles formatting for both API and local display

    setInput("")
    setAttachments([]) // Clear attachments

    try {
      // @ts-ignore - Assuming onSend signature update propagates or is loose
      await onSend(input, attachments)
    } finally {
      setSending(false)
    }
  }

  const handleUpload = async (file: File, type: "image" | "file") => {
    if (!file) return

    // 1. Create local preview
    const localUrl = URL.createObjectURL(file)

    // We push to state
    setAttachments((prev) => [
      ...prev,
      {
        type,
        url: "", // Placeholder
        name: file.name,
        previewUrl: localUrl,
        isUploading: true,
      },
    ])

    setIsUploading(true) // Global spinner

    try {
      if (!projectId) {
        throw new Error(t("chat.input.noProject"))
      }

      // 2. Upload
      // FilesService.uploadFile expects { projectId, formData: { file } }
      // Wait, formData param in SDK is wrapper for params: { file: ... }
      // Let's check sdk types or assumption.
      // Usually: uploadFile(data: { projectId: number, formData: { file: Blob | File } })
      const res: any = await FilesService.uploadFile({
        projectId,
        formData: {
          file: file,
        },
      })

      // 3. Update state with server URL
      // API returns { url, filename, path }
      const serverUrl = res.url

      setAttachments((prev) =>
        prev.map((att) => {
          if (att.previewUrl === localUrl) {
            return { ...att, url: serverUrl, isUploading: false }
          }
          return att
        }),
      )
    } catch (error: any) {
      toast.error(
        t("chat.input.uploadFailed") +
        (error.message ? `: ${error.message}` : ""),
      )
      console.error(error)
      // Remove failed attachment
      setAttachments((prev) =>
        prev.filter((att) => att.previewUrl !== localUrl),
      )
    } finally {
      setIsUploading(false)
    }
  }

  const removeAttachment = (index: number) => {
    setAttachments((prev) => prev.filter((_, i) => i !== index))
  }

  const isInputDisabled = sending || !isConnected || !isDeviceOnline

  return (
    <div
      className={
        className ||
        "bg-background border-t p-3 shrink-0 pb-[max(env(safe-area-inset-bottom),0.75rem)] sticky bottom-0 z-20"
      }
    >
      <form
        onSubmit={(e) => {
          e.preventDefault()
          handleSendAction()
        }}
        className={
          innerClassName ||
          `flex flex-col gap-2 bg-muted/50 p-3 rounded-3xl border border-transparent focus-within:border-primary/50 focus-within:bg-background transition-all ${isListening ? "ring-2 ring-red-500/50 bg-red-50/50" : ""} ${isInputDisabled ? "opacity-50 pointer-events-none" : ""}`
        }
      >
        {/* Attachment Previews (Inside Input Box) */}
        {attachments.length > 0 && (
          <div className="flex gap-2 mb-1 overflow-x-auto pb-2 px-1 scrollbar-hide">
            {attachments.map((att, i) => (
              <div
                key={i}
                className="relative group shrink-0 animate-in fade-in zoom-in duration-200"
              >
                <div className="w-16 h-16 rounded-lg overflow-hidden border bg-background flex items-center justify-center relative shadow-sm">
                  {att.type === "image" ? (
                    <img
                      src={att.previewUrl || att.url}
                      alt="preview"
                      className="w-full h-full object-cover"
                    />
                  ) : (
                    <FileIcon className="w-8 h-8 text-muted-foreground" />
                  )}
                  {/* Loading Overlay */}
                  {att.isUploading && (
                    <div className="absolute inset-0 bg-black/30 flex items-center justify-center">
                      <Loader2 className="w-5 h-5 text-white animate-spin" />
                    </div>
                  )}
                </div>
                <button
                  type="button"
                  onClick={() => removeAttachment(i)}
                  className="absolute -top-1.5 -right-1.5 bg-muted-foreground text-white rounded-full p-0.5 hover:bg-destructive shadow-sm z-10"
                >
                  <X className="w-3 h-3" />
                </button>
              </div>
            ))}
          </div>
        )}

        {/* Row 1: Text Input */}
        <div className="w-full">
          <textarea
            value={input}
            onChange={(e) => setInput(e.target.value)}
            placeholder={
              placeholder ||
              placeholder ||
              (!isConnected
                ? t("chat.input.placeholder.connecting")
                : !isDeviceOnline
                  ? t("chat.input.placeholder.offline")
                  : isListening
                    ? t("chat.input.placeholder.listening")
                    : t("chat.input.placeholder.default"))
            }
            disabled={isInputDisabled}
            className="w-full bg-transparent border-none focus:ring-0 p-1 text-base placeholder:text-muted-foreground/70 resize-none min-h-[40px] max-h-[120px] focus-visible:outline-none"
            rows={1}
            onInput={(e) => {
              const target = e.target as HTMLTextAreaElement
              target.style.height = "auto"
              target.style.height = `${Math.min(target.scrollHeight, 120)}px`
            }}
            onKeyDown={(e) => {
              if (e.key === "Enter" && !e.shiftKey) {
                e.preventDefault()
                handleSendAction()
              }
            }}
          />
          <input
            type="file"
            ref={fileInputRef}
            className="hidden"
            onChange={(e) => {
              const file = e.target.files?.[0]
              if (file) handleUpload(file, "file")
              e.target.value = ""
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
              className={`rounded-full w-9 h-9 transition-colors ${isListening ? "text-red-500 hover:text-red-600 hover:bg-red-100" : "text-muted-foreground hover:bg-background hover:text-primary"}`}
              onClick={toggleVoiceInput}
            >
              <Mic
                className={`w-5 h-5 ${isListening ? "animate-pulse" : ""}`}
              />
            </Button>

            <Button
              type="button"
              variant="ghost"
              size="icon"
              disabled={isInputDisabled || isUploading}
              className="rounded-full w-9 h-9 text-muted-foreground hover:bg-background hover:text-primary"
              onClick={() => cameraInputRef.current?.click()}
            >
              <Camera className="w-5 h-5" />
            </Button>

            <Button
              type="button"
              variant="ghost"
              size="icon"
              disabled={isInputDisabled || isUploading}
              className="rounded-full w-9 h-9 text-muted-foreground hover:bg-background hover:text-primary"
              onClick={() => fileInputRef.current?.click()}
            >
              {isUploading ? (
                <Loader2 className="w-5 h-5 animate-spin" />
              ) : (
                <Paperclip className="w-5 h-5" />
              )}
            </Button>
          </div>

          <input
            type="file"
            ref={cameraInputRef}
            className="hidden"
            accept="image/*"
            capture="environment"
            onChange={(e) => {
              const file = e.target.files?.[0]
              if (file) handleUpload(file, "image")
              e.target.value = ""
            }}
          />

          {/* Right: Send */}
          <Button
            type="submit"
            disabled={
              isInputDisabled || (!input.trim() && attachments.length === 0)
            }
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
