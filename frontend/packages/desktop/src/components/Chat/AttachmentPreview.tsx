import { File as FileIcon, X, MessageSquare } from "lucide-react"
import { cn } from "@evoloop/shared/lib/utils"

export interface Attachment {
  id: string
  url: string
  name: string
  type: "image" | "file" | "reference" | "message"
}

interface AttachmentPreviewProps {
  attachments: Attachment[]
  onRemove: (id: string) => void
}

export function AttachmentPreview({
  attachments,
  onRemove,
}: AttachmentPreviewProps) {
  if (attachments.length === 0) return null

  return (
    <div className="flex gap-2 p-2 overflow-x-auto">
      {attachments.map((att) => (
        <div
          key={att.id}
          className={cn(
            "relative group flex items-center gap-2 pr-7 pl-2 py-1.5 rounded-md border text-xs font-medium transition-all animate-in fade-in zoom-in-95",
            att.type === "message"
              ? "bg-green-500/10 border-green-500/20 text-green-700 dark:text-green-400"
              : att.type === "image"
                ? "bg-purple-500/10 border-purple-500/20 text-purple-700 dark:text-purple-400"
                : "bg-blue-500/10 border-blue-500/20 text-blue-700 dark:text-blue-400"
          )}
          title={att.name}
        >
          {att.type === "image" ? (
            <div className="relative w-4 h-4 overflow-hidden rounded-sm shrink-0">
              <img src={att.url} alt="preview" className="w-full h-full object-cover" />
            </div>
          ) : att.type === "message" ? (
            <MessageSquare className="w-3.5 h-3.5 shrink-0 opacity-70" />
          ) : (
            <FileIcon className="w-3.5 h-3.5 shrink-0 opacity-70" />
          )}

          <span className="truncate max-w-[120px]">{att.name}</span>

          <button
            onClick={() => onRemove(att.id)}
            className="absolute right-1 top-1/2 -translate-y-1/2 p-0.5 rounded-full hover:bg-black/10 dark:hover:bg-white/10 opacity-60 hover:opacity-100 transition-opacity"
          >
            <X size={12} />
          </button>
        </div>
      ))}
    </div>
  )
}
