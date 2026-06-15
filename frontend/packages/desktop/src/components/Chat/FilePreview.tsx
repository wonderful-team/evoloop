import { cn } from "@evoloop/shared/lib/utils"
import {
  AlertCircle,
  File as FileIcon,
  Loader2,
  MessageSquare,
  Music,
  X,
} from "lucide-react"
import { useTranslation } from "react-i18next"

export interface PickedFile {
  id: string
  url: string | number // Can be string (URL) or number (skill ID)
  name: string
  type: "image" | "file" | "reference" | "message" | "audio" | "skill"
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
}

export function FilePreview({ pickedFiles, onRemove }: FilePreviewProps) {
  const { t } = useTranslation()
  if (pickedFiles.length === 0) return null

  return (
    <div className="flex gap-2 p-2 overflow-x-auto">
      {pickedFiles.map((file) => (
        <div
          key={file.id}
          className={cn(
            "relative group flex items-center gap-2 pr-7 pl-2 py-1.5 rounded-md border border-border text-xs font-medium transition-all animate-in fade-in zoom-in-95",
            file.status === "error"
              ? "bg-red-500/10 border-red-500/20 text-red-700 dark:text-red-400"
              : file.type === "message"
                ? "bg-green-500/10 border-green-500/20 text-green-700 dark:text-green-400"
                : file.type === "image"
                  ? "bg-purple-500/10 border-purple-500/20 text-purple-700 dark:text-purple-400"
                  : file.type === "audio"
                    ? "bg-amber-500/10 border-amber-500/20 text-amber-700 dark:text-amber-400"
                    : file.type === "skill"
                      ? "bg-indigo-500/10 border-indigo-500/20 text-indigo-700 dark:text-indigo-400"
                      : "bg-blue-500/10 border-blue-500/20 text-blue-700 dark:text-blue-400",
            file.status === "uploading" && "opacity-70",
          )}
          title={file.name}
        >
          {file.status === "uploading" ? (
            <Loader2 className="w-3.5 h-3.5 shrink-0 animate-spin opacity-70" />
          ) : file.status === "error" ? (
            <AlertCircle className="w-3.5 h-3.5 shrink-0 text-red-500" />
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
            <Music className="w-3.5 h-3.5 shrink-0 text-amber-500" />
          ) : file.type === "skill" ? (
            <span className="w-3.5 h-3.5 shrink-0 text-purple-500 font-bold text-[10px]">
              S
            </span>
          ) : (
            <FileIcon className="w-3.5 h-3.5 shrink-0 opacity-70" />
          )}

          <div className="flex flex-col min-w-0">
            <span className="truncate max-w-[120px]">{file.name}</span>
            {file.status === "uploading" && (
              <span className="text-[9px] text-muted-foreground opacity-80 mt-0.5">
                {t("chat.interface.uploading", "上传中...")}
              </span>
            )}
            {file.status === "error" && (
              <span className="text-[9px] text-red-500 mt-0.5">
                {t("chat.interface.uploadFailed", "上传失败")}
              </span>
            )}
          </div>

          <button
            onClick={() => onRemove(file.id)}
            className="absolute right-1 top-1/2 -translate-y-1/2 p-0.5 rounded-full hover:bg-black/10 dark:hover:bg-white/10 opacity-60 hover:opacity-100 transition-opacity"
          >
            <X size={12} />
          </button>
        </div>
      ))}
    </div>
  )
}
