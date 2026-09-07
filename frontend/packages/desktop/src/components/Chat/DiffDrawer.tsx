import { ScrollArea } from "@evoloop/shared/components/ui/scroll-area"
import * as Diff2Html from "diff2html"
import { useEffect, useState } from "react"
import "diff2html/bundles/css/diff2html.min.css"
import { FileDiff } from "lucide-react"
import { useTranslation } from "react-i18next"
import { AppSheet } from "@/components/Common/AppSheet"

interface DiffDrawerProps {
  isOpen: boolean
  onClose: () => void
  path: string | null
  diff: string | null
}

export function DiffDrawer({ isOpen, onClose, path, diff }: DiffDrawerProps) {
  const { t } = useTranslation()

  const [htmlObj, setHtmlObj] = useState("")
  const [isRendering, setIsRendering] = useState(false)

  useEffect(() => {
    if (!isOpen || !diff) {
      setHtmlObj("")
      return
    }

    setIsRendering(true)
    const timer = setTimeout(() => {
      try {
        const html = Diff2Html.html(diff, {
          drawFileList: false,
          matching: "lines",
          outputFormat: "side-by-side",
          colorScheme: "dark",
        })
        setHtmlObj(html)
      } catch (e) {
        console.error("Failed to parse diff", e)
        setHtmlObj("")
      } finally {
        setIsRendering(false)
      }
    }, 50) // Short delay to allow drawer animation to start

    return () => clearTimeout(timer)
  }, [diff, isOpen])

  if (!path || !diff) return null

  return (
    <AppSheet
      open={isOpen}
      onOpenChange={(open) => !open && onClose()}
      title={path.split("/").pop()}
      subtitle={path}
      icon={<FileDiff />}
      footer={
        <div className="p-3 font-mono text-[10px] text-muted-foreground/50 text-center shrink-0">
          {t("chat.diff.tip")}
        </div>
      }
    >
      <ScrollArea className="flex-1 bg-background min-h-0">
        <style>{`
                        .d2h-file-header { display: none !important; }
                        .d2h-file-wrapper { border: none !important; margin-bottom: 0 !important; background: transparent !important; }
                        .d2h-diff-table { table-layout: fixed !important; width: 100% !important; background: transparent !important; }
                        .d2h-diff-tbody, .d2h-file-list-wrapper, .d2h-wrapper { background: transparent !important; }
                        .d2h-code-line { padding: 0 4px !important; }
                        .d2h-code-side-linenumber {
                            display: table-cell !important;
                            position: static !important;
                            width: 48px !important;
                            min-width: 48px !important;
                            max-width: 48px !important;
                            padding: 0 8px !important;
                            background: transparent !important;
                            border-color: transparent !important;
                            color: var(--muted-foreground) !important;
                            opacity: 0.6;
                            font-family: var(--font-mono) !important;
                        }
                        .d2h-code-side-line {
                            display: block !important;
                            width: 100% !important;
                            padding-left: 0.5em !important;
                            padding-right: 0.5em !important;
                            font-family: var(--font-mono) !important;
                        }
                        .d2h-code-line-ctn {
                            white-space: pre-wrap !important;
                            word-break: break-all !important;
                        }
                        /* 增删行底色 → 语义 token 低饱和 tint（对齐 Engineering Premium 日志色纪律） */
                        .d2h-ins { background: rgba(74, 222, 128, 0.07) !important; }
                        .d2h-del { background: rgba(248, 113, 113, 0.07) !important; }
                        .d2h-info { background: rgba(255, 255, 255, 0.03) !important; }
                    `}</style>
        {isRendering ? (
          <div className="w-full h-full flex items-center justify-center text-muted-foreground p-8">
            <div className="animate-spin rounded-full h-6 w-6 border-b-2 border-primary mr-3" />
            {t("common.loading")}
          </div>
        ) : (
          <div
            className="w-full h-full p-4 overflow-x-auto text-sm"
            dangerouslySetInnerHTML={{ __html: htmlObj }}
            style={{ color: "var(--foreground)" }}
          />
        )}
      </ScrollArea>
    </AppSheet>
  )
}
