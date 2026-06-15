import { ScrollArea } from "@evoloop/shared/components/ui/scroll-area"
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
} from "@evoloop/shared/components/ui/sheet"
import * as Diff2Html from "diff2html"
import { useEffect, useState } from "react"
import "diff2html/bundles/css/diff2html.min.css"
import { FileDiff } from "lucide-react"
import { useTranslation } from "react-i18next"

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
    <Sheet open={isOpen} onOpenChange={(open) => !open && onClose()}>
      <SheetContent
        side="right"
        className="!max-w-[calc(100vw-360px)] w-full p-0 flex flex-col gap-0 border-l border-border shadow-2xl"
      >
        <SheetHeader className="p-4 border-b border-border bg-muted/20 shrink-0">
          <SheetDescription className="sr-only">
            Diff View for {path.split("/").pop()}
          </SheetDescription>
          <div className="flex items-center gap-3">
            <div className="p-2 bg-primary/10 rounded-md">
              <FileDiff className="h-5 w-5 text-primary" />
            </div>
            <div className="flex flex-col min-w-0">
              <SheetTitle className="text-sm font-semibold truncate leading-none">
                {path.split("/").pop()}
              </SheetTitle>
              <span className="text-[10px] text-muted-foreground font-mono mt-1 opacity-70 truncate">
                {path}
              </span>
            </div>
          </div>
        </SheetHeader>

        <ScrollArea className="flex-1 bg-background">
          <style>{`
                        .d2h-file-header { display: none !important; }
                        .d2h-file-wrapper { border: none !important; margin-bottom: 0 !important; }
                        .d2h-diff-table { table-layout: fixed !important; width: 100% !important; }
                        .d2h-code-line { padding: 0 4px !important; }
                        .d2h-code-side-linenumber { 
                            display: table-cell !important;
                            position: static !important; 
                            width: 48px !important; 
                            min-width: 48px !important; 
                            max-width: 48px !important; 
                            padding: 0 8px !important; 
                        }
                        .d2h-code-side-line { 
                            display: block !important;
                            width: 100% !important; 
                            padding-left: 0.5em !important; 
                            padding-right: 0.5em !important; 
                        }
                        .d2h-code-line-ctn { 
                            white-space: pre-wrap !important; 
                            word-break: break-all !important; 
                        }
                    `}</style>
          {isRendering ? (
            <div className="w-full h-full flex items-center justify-center text-muted-foreground p-8">
              <div className="animate-spin rounded-full h-6 w-6 border-b-2 border-primary mr-3" />
              {t("common.loading", { defaultValue: "Loading..." })}
            </div>
          ) : (
            <div
              className="w-full h-full p-4 overflow-x-auto text-sm"
              dangerouslySetInnerHTML={{ __html: htmlObj }}
              style={{ color: "var(--foreground)" }}
            />
          )}
        </ScrollArea>

        <div className="p-3 border-t border-border bg-muted/10 text-[10px] text-muted-foreground text-center shrink-0 italic">
          {t("chat.diff.tip")}
        </div>
      </SheetContent>
    </Sheet>
  )
}
