import { Button } from "@evoloop/shared/components/ui/button"
import {
  Dialog,
  DialogContent,
  DialogTitle,
} from "@evoloop/shared/components/ui/dialog"
import { cn } from "@evoloop/shared/lib/utils"
import {
  BookOpen,
  Brain,
  ChevronDown,
  FileText,
  Image as ImageIcon,
  Music,
  Search,
  Terminal,
  X,
} from "lucide-react"
import { memo, useState } from "react"
import { useTranslation } from "react-i18next"

interface Reference {
  type: "memory" | "file" | "search" | "tool" | "image" | "file_image" | string
  name: string
  path?: string
  content?: string
  target_id?: string
}

interface SourcesFooterProps {
  references: Reference[]
  maxVisible?: number
}

// 判断是否为图片类型引用
const isImageReference = (ref: Reference): boolean => {
  const imageTypes = ["image", "file_image", "screenshot"]
  if (imageTypes.includes(ref.type)) return true
  // 根据文件扩展名判断
  const imageExtensions = [".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp"]
  const targetPath = ref.path || ref.target_id || ""
  return imageExtensions.some((ext) => targetPath.toLowerCase().includes(ext))
}

// 判断是否为音频类型引用
const isAudioReference = (ref: Reference): boolean => {
  const audioTypes = ["audio", "voice", "recording"]
  if (audioTypes.includes(ref.type)) return true
  // 根据文件扩展名判断
  const audioExtensions = [
    ".mp3",
    ".wav",
    ".ogg",
    ".m4a",
    ".flac",
    ".aac",
    ".opus",
  ]
  const targetPath = ref.path || ref.target_id || ""
  return audioExtensions.some((ext) => targetPath.toLowerCase().includes(ext))
}

// 获取图片URL
const getImageUrl = (ref: Reference): string | null => {
  return ref.path || ref.target_id || ref.content || null
}

/**
 * ImagePreview - 图片引用预览组件
 */
function ImagePreview({ ref, index }: { ref: Reference; index: number }) {
  const { t } = useTranslation()
  const [isOpen, setIsOpen] = useState(false)
  const imageUrl = getImageUrl(ref)

  if (!imageUrl) return null

  return (
    <>
      <button
        type="button"
        onClick={() => setIsOpen(true)}
        className={cn(
          "group relative inline-flex items-center gap-1.5 px-2 py-1 rounded-md",
          "bg-purple-500/10 hover:bg-purple-500/20",
          "border border-purple-500/20 hover:border-purple-500/40",
          "transition-all cursor-zoom-in",
        )}
        title={ref.name}
      >
        <ImageIcon size={14} className="text-purple-500 shrink-0" />
        <span className="text-xs text-purple-700 dark:text-purple-300 max-w-[80px] truncate">
          {ref.name}
        </span>
        {/* 缩略图预览（悬停时显示） */}
        <div className="absolute bottom-full left-1/2 -translate-x-1/2 mb-2 opacity-0 group-hover:opacity-100 transition-opacity pointer-events-none z-50">
          <div className="bg-popover border rounded-lg shadow-lg p-1">
            <img
              src={imageUrl}
              alt={ref.name}
              className="max-w-[120px] max-h-[120px] rounded object-cover"
              onError={(e) => {
                // 图片加载失败时隐藏预览
                ;(e.target as HTMLImageElement).style.display = "none"
              }}
            />
          </div>
        </div>
      </button>

      {/* 大图查看器 */}
      <Dialog open={isOpen} onOpenChange={setIsOpen}>
        <DialogContent className="max-w-4xl max-h-[90vh] p-0 bg-black/90 border-none">
          <DialogTitle className="sr-only">
            {t("chat.sources.imagePreview", "Image Preview")} - {ref.name}
          </DialogTitle>
          <div className="relative w-full h-full flex items-center justify-center p-4">
            <img
              src={imageUrl}
              alt={ref.name}
              className="max-w-full max-h-[85vh] object-contain rounded-lg"
            />
            <Button
              variant="ghost"
              size="icon"
              className="absolute top-4 right-4 text-white/70 hover:text-white hover:bg-white/20 rounded-full"
              onClick={() => setIsOpen(false)}
            >
              <X className="w-6 h-6" />
            </Button>
            <div className="absolute bottom-4 left-4 right-4 text-center">
              <span className="text-sm text-white/80 bg-black/50 px-3 py-1 rounded-full">
                {ref.name}
              </span>
            </div>
          </div>
        </DialogContent>
      </Dialog>
    </>
  )
}

/**
 * SourcesFooter - Displays message sources with collapse/expand for >3 items
 */
export const SourcesFooter = memo(
  ({ references, maxVisible = 3 }: SourcesFooterProps) => {
    const { t } = useTranslation()
    const [isExpanded, setIsExpanded] = useState(false)

    if (!references || references.length === 0) return null

    const visibleRefs = isExpanded
      ? references
      : references.slice(0, maxVisible)
    const hiddenCount = references.length - maxVisible

    const getIcon = (type: string) => {
      switch (type) {
        case "memory":
          return <Brain size={14} className="text-amber-500" />
        case "file":
          return <FileText size={14} className="text-blue-500" />
        case "search":
          return <Search size={14} className="text-purple-500" />
        case "tool":
          return <Terminal size={14} className="text-slate-500" />
        case "image":
        case "file_image":
          return <ImageIcon size={14} className="text-purple-500" />
        case "audio":
          return <Music size={14} className="text-amber-500" />
        default:
          return <BookOpen size={14} className="text-muted-foreground" />
      }
    }

    return (
      <div className="mt-6 pt-4 border-t border-[var(--doc-border)]/50">
        <div className="flex items-center gap-3 flex-wrap">
          <span className="text-[10px] font-bold uppercase tracking-[0.15em] text-muted-foreground/40 shrink-0">
            {t("chat.sources.title", "References")}
          </span>
          {visibleRefs.map((ref, idx) => {
            // 图片类型引用使用专门的预览组件
            if (isImageReference(ref)) {
              return (
                <ImagePreview
                  key={`${ref.type}-${ref.name}-${idx}`}
                  ref={ref}
                  index={idx}
                />
              )
            }

            // 音频类型引用使用特殊样式
            if (isAudioReference(ref)) {
              return (
                <span
                  key={`${ref.type}-${ref.name}-${idx}`}
                  className={cn(
                    "inline-flex items-center gap-1 px-1.5 py-0.5 rounded-md",
                    "bg-amber-500/10 text-xs text-amber-700 dark:text-amber-400",
                    "border border-amber-500/20",
                    "hover:bg-amber-500/20 transition-colors cursor-default",
                  )}
                  title={ref.path || ref.target_id || ref.name}
                >
                  <Music size={14} className="text-amber-500" />
                  <span className="max-w-[100px] truncate">{ref.name}</span>
                </span>
              )
            }

            // 其他类型保持原有样式
            return (
              <span
                key={`${ref.type}-${ref.name}-${idx}`}
                className={cn(
                  "inline-flex items-center gap-1.5 px-2 py-1 rounded-md transition-colors",
                  "bg-muted/10 text-[11px] font-medium text-muted-foreground/70",
                  "hover:bg-muted/20 cursor-default border border-transparent hover:border-border/40",
                )}
                title={ref.path || ref.content || ref.name}
              >
                <span className="opacity-70">{getIcon(ref.type)}</span>
                <span className="max-w-[120px] truncate">{ref.name}</span>
              </span>
            )
          })}
          {hiddenCount > 0 && !isExpanded && (
            <Button
              variant="ghost"
              size="sm"
              className="h-5 px-1.5 text-xs text-muted-foreground hover:text-foreground"
              onClick={() => setIsExpanded(true)}
            >
              +{hiddenCount} {t("chat.sources.more", "more")}
              <ChevronDown size={12} className="ml-0.5" />
            </Button>
          )}
          {isExpanded && hiddenCount > 0 && (
            <Button
              variant="ghost"
              size="sm"
              className="h-5 px-1.5 text-xs text-muted-foreground hover:text-foreground"
              onClick={() => setIsExpanded(false)}
            >
              {t("chat.sources.showLess", "Show less")}
            </Button>
          )}
        </div>
      </div>
    )
  },
)

SourcesFooter.displayName = "SourcesFooter"
