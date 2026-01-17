import { FileText, Image as ImageIcon, X, MessageSquare, Link } from "lucide-react"
import { Button } from "@/components/ui/button"

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
        <div key={att.id} className="relative group shrink-0">
          <div className="flex items-center gap-2 px-3 py-2 bg-muted/40 border rounded-lg text-xs max-w-[200px]">
            {att.type === "image" ? (
              <ImageIcon className="w-4 h-4 text-purple-500 shrink-0" />
            ) : att.type === "message" ? (
              <MessageSquare className="w-4 h-4 text-green-500 shrink-0" />
            ) : att.type === "reference" ? (
              <Link className="w-4 h-4 text-orange-500 shrink-0" />
            ) : (
              <FileText className="w-4 h-4 text-blue-500 shrink-0" />
            )}
            <span className="truncate font-medium">{att.name}</span>
          </div>

          <Button
            variant="destructive"
            size="icon"
            className="absolute -top-1 -right-1 w-5 h-5 rounded-full opacity-0 group-hover:opacity-100 transition-opacity shadow-sm"
            onClick={() => onRemove(att.id)}
          >
            <X className="w-3 h-3" />
          </Button>
        </div>
      ))}
    </div>
  )
}
