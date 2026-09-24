import {Button} from "@evoloop/shared/components/ui/button"
import {Dialog, DialogContent, DialogTitle,} from "@evoloop/shared/components/ui/dialog"
import {ChevronLeft, ChevronRight, X} from "lucide-react"
import {useCallback, useEffect} from "react"
import {useTranslation} from "react-i18next"
import {resolveLocalFileSrc} from "@/utils/fileUtils"

export interface GalleryImage {
  url: string
  name: string
}

interface ImageGalleryViewerProps {
  images: GalleryImage[]
  index: number
  open: boolean
  onIndexChange: (index: number) => void
  onClose: () => void
}

/**
 * 全屏图片查看器（Gallery 视图）：
 * 左右切换、底部缩略图条、键盘 ←/→ 导航、Esc 关闭。
 */
export function ImageGalleryViewer({
  images,
  index,
  open,
  onIndexChange,
  onClose,
}: ImageGalleryViewerProps) {
  const { t } = useTranslation()

  const current = images[index]
  const go = useCallback(
    (delta: number) => {
      if (images.length === 0) return
      onIndexChange((index + delta + images.length) % images.length)
    },
    [images.length, index, onIndexChange],
  )

  useEffect(() => {
    if (!open) return
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "ArrowLeft") go(-1)
      else if (e.key === "ArrowRight") go(1)
    }
    window.addEventListener("keydown", onKey)
    return () => window.removeEventListener("keydown", onKey)
  }, [open, go])

  if (!current) return null

  return (
    <Dialog open={open} onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="w-screen h-screen max-w-none sm:max-w-none rounded-none sm:rounded-none border-none bg-black/95 p-0 gap-0 flex flex-col overflow-hidden">
        <DialogTitle className="sr-only">
          {t("chat.messageList.imageViewer")}
        </DialogTitle>

        {/* 顶栏：计数 + 关闭 */}
        <div className="flex items-center justify-between px-4 py-2 text-white/70 text-sm shrink-0">
          <span>
            {images.length > 1 ? `${index + 1} / ${images.length}` : ""}
          </span>
          <Button
            variant="ghost"
            size="icon"
            className="text-white/70 hover:text-white hover:bg-white/20 rounded-full"
            onClick={onClose}
          >
            <X className="w-5 h-5" />
          </Button>
        </div>

        {/* 主视图 */}
        <div className="relative flex-1 flex items-center justify-center min-h-0 px-12">
          {images.length > 1 && (
            <Button
              variant="ghost"
              size="icon"
              className="absolute left-2 top-1/2 -translate-y-1/2 z-10 h-10 w-10 text-white/70 hover:text-white hover:bg-white/20 rounded-full"
              onClick={() => go(-1)}
            >
              <ChevronLeft className="w-7 h-7" />
            </Button>
          )}
          <img
            key={current.url}
            src={resolveLocalFileSrc(current.url)}
            alt={current.name}
            className="max-w-full max-h-full object-contain select-none"
            draggable={false}
          />
          {images.length > 1 && (
            <Button
              variant="ghost"
              size="icon"
              className="absolute right-2 top-1/2 -translate-y-1/2 z-10 h-10 w-10 text-white/70 hover:text-white hover:bg-white/20 rounded-full"
              onClick={() => go(1)}
            >
              <ChevronRight className="w-7 h-7" />
            </Button>
          )}
        </div>

        {/* 缩略图条 */}
        {images.length > 1 && (
          <div className="flex items-center gap-2 px-4 py-3 overflow-x-auto shrink-0">
            {images.map((img, i) => (
              <button
                key={img.url}
                type="button"
                onClick={() => onIndexChange(i)}
                className={`h-14 w-14 shrink-0 rounded-md overflow-hidden border transition-all ${
                  i === index
                    ? "border-white ring-2 ring-white/60 opacity-100"
                    : "border-white/20 opacity-50 hover:opacity-80"
                }`}
              >
                <img
                  src={resolveLocalFileSrc(img.url)}
                  alt={img.name}
                  className="w-full h-full object-cover"
                  loading="lazy"
                  draggable={false}
                />
              </button>
            ))}
          </div>
        )}
      </DialogContent>
    </Dialog>
  )
}
