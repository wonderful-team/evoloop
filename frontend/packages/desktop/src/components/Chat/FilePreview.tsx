import {cn} from "@evoloop/shared/lib/utils"
import {AlertCircle, File as FileIcon, Folder, Loader2, MessageSquare, Music, X,} from "lucide-react"
import {useTranslation} from "react-i18next"

export interface PickedFile {
  id: string
  url: string | number // Can be string (URL) or number (skill ID)
  name: string
  type:
    | "image"
    | "file"
    | "reference"
    | "message"
    | "audio"
    | "skill"
    | "directory"
  status?: "uploading" | "success" | "error"
  metadata?: {
    duration?: number
    waveform?: number[]
    localPath?: string
    skill_id?: number
    skill_name?: string
    [key: string]: any
  }
}

interface FilePreviewProps {
  pickedFiles: PickedFile[]
  onRemove: (id: string) => void
  onClick?: (file: PickedFile) => void
}

export function FilePreview({
  pickedFiles,
  onRemove,
  onClick,
}: FilePreviewProps) {
  const { t } = useTranslation()
  if (pickedFiles.length === 0) return null

  return (
    <div className="flex gap-2 p-2 overflow-x-auto">
      {pickedFiles.map((file) => (
        <div
          key={file.id}
          onClick={() => onClick?.(file)}
          className={cn(
            "relative group flex items-center gap-2 pr-7 pl-2 py-1.5 rounded-md border border-border text-xs font-medium transition-all animate-in fade-in zoom-in-95",
            onClick && "cursor-pointer hover:ring-1 hover:ring-border",
            file.status === "error"
              ? "bg-destructive/10 border-destructive/20 text-destructive"
              : file.type === "message"
                ? "bg-success/10 border-success/20 text-success"
                : file.type === "image"
                  ? "bg-signal-purple/10 border-signal-purple/20 text-signal-purple"
                  : file.type === "audio"
                    ? "bg-warning/10 border-warning/20 text-warning"
                    : file.type === "directory"
                      ? "bg-warning/10 border-warning/20 text-warning"
                      : file.type === "skill"
                        ? "bg-signal-purple/10 border-signal-purple/20 text-signal-purple"
                        : "bg-info/10 border-info/20 text-info",
            file.status === "uploading" && "opacity-70",
          )}
          title={file.name}
        >
          {file.status === "uploading" ? (
            <Loader2 className="w-3.5 h-3.5 shrink-0 animate-spin opacity-70" />
          ) : file.status === "error" ? (
            <AlertCircle className="w-3.5 h-3.5 shrink-0 text-destructive" />
          ) : file.type === "image" ? (
            <div className="relative w-4 h-4 overflow-hidden rounded-sm shrink-0">
              <img
                src={String(file.url)}
                alt={t("common.preview")}
                className="w-full h-full object-cover"
              />
            </div>
          ) : file.type === "message" ? (
            <MessageSquare className="w-3.5 h-3.5 shrink-0 opacity-70" />
          ) : file.type === "audio" ? (
            <Music className="w-3.5 h-3.5 shrink-0 text-warning" />
          ) : file.type === "directory" ? (
            <Folder className="w-3.5 h-3.5 shrink-0 text-warning" />
          ) : file.type === "skill" ? (
            <span className="w-3.5 h-3.5 shrink-0 text-signal-purple font-bold text-[10px]">
              S
            </span>
          ) : (
            <FileIcon className="w-3.5 h-3.5 shrink-0 opacity-70" />
          )}

          <div className="flex flex-col min-w-0">
            <span className="truncate max-w-[120px]">{file.name}</span>
            {file.status === "uploading" && (
              <span className="text-[9px] text-muted-foreground opacity-80 mt-0.5">
                {t("chat.interface.uploading")}
              </span>
            )}
            {file.status === "error" && (
              <span className="text-[9px] text-destructive mt-0.5">
                {t("chat.interface.uploadFailed")}
              </span>
            )}
          </div>

          <button
            onClick={(e) => {
              e.stopPropagation()
              onRemove(file.id)
            }}
            className="absolute right-1 top-1/2 -translate-y-1/2 p-0.5 rounded-full hover:bg-black/10 dark:hover:bg-white/10 opacity-60 hover:opacity-100 transition-opacity"
          >
            <X size={12} />
          </button>
        </div>
      ))}
    </div>
  )
}
