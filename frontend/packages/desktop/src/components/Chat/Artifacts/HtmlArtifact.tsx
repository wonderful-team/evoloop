import { Button } from "@evoloop/shared/components/ui/button"
import { useInView } from "framer-motion"
import { Check, Copy, ExternalLink, Maximize2, Minimize2 } from "lucide-react"
import React from "react"
import ReactDOM from "react-dom"
import { useTranslation } from "react-i18next"

interface HtmlArtifactProps {
  data: {
    title?: string
    html: string
    css?: string
    js?: string
    height?: number
  }
}

export const HtmlArtifact: React.FC<HtmlArtifactProps> = ({ data }) => {
  const { t } = useTranslation()
  const [isFullscreen, setIsFullscreen] = React.useState(false)
  const [copied, setCopied] = React.useState(false)
  const containerRef = React.useRef<HTMLDivElement>(null)
  const inView = useInView(containerRef, { margin: "200px" })

  const fullHtml = React.useMemo(() => {
    return `
      <!DOCTYPE html>
      <html>
        <head>
          <meta charset="utf-8">
          <meta name="viewport" content="width=device-width, initial-scale=1.0">
          <style>
            body { margin: 0; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif; background: transparent; }
            ${data.css || ""}
          </style>
        </head>
        <body>
          ${data.html || ""}
          <script>${data.js || ""}</script>
        </body>
      </html>
    `
  }, [data.html, data.css, data.js])

  const handleCopy = React.useCallback(() => {
    navigator.clipboard.writeText(data.html || "")
    setCopied(true)
    setTimeout(() => setCopied(false), 2000)
  }, [data.html])

  const handleOpenNewWindow = React.useCallback(() => {
    const blob = new Blob([fullHtml], { type: "text/html" })
    const url = URL.createObjectURL(blob)
    const newWindow = window.open(url, "_blank")
    if (newWindow) {
      newWindow.opener = null
    }
  }, [fullHtml])

  const renderFullscreenModal = () => {
    if (!isFullscreen) return null
    return ReactDOM.createPortal(
      <div className="fixed inset-0 z-[9999] bg-black/80 backdrop-blur-md flex items-center justify-center p-6 animate-in fade-in zoom-in-95 duration-200">
        <div className="w-full h-full max-w-7xl max-h-[90vh] flex flex-col bg-background border border-[var(--doc-border)] rounded-2xl overflow-hidden shadow-2xl">
          <div className="py-4 px-6 border-b border-[var(--doc-border)] bg-muted/20 flex items-center justify-between">
            <h3 className="text-base font-bold tracking-tight">
              {data.title || t("chat.artifact.htmlPreview", "HTML Preview")}
            </h3>
            <div className="flex items-center gap-2">
              <Button
                variant="ghost"
                size="icon"
                className="h-8 w-8 rounded-full hover:bg-muted/50"
                onClick={handleOpenNewWindow}
                title={t("common.open")}
              >
                <ExternalLink className="w-4 h-4 text-muted-foreground" />
              </Button>
              <Button
                variant="ghost"
                size="icon"
                className="h-8 w-8 rounded-full hover:bg-muted/50"
                onClick={() => setIsFullscreen(false)}
                title={t("common.close", "Close")}
              >
                <Minimize2 className="w-4 h-4 text-muted-foreground" />
              </Button>
            </div>
          </div>
          <div className="flex-1 bg-white dark:bg-zinc-900 overflow-hidden relative">
            <iframe
              title="HTML Preview Fullscreen"
              srcDoc={fullHtml}
              className="w-full h-full border-none"
              sandbox="allow-scripts allow-same-origin"
            />
          </div>
        </div>
      </div>,
      document.body,
    )
  }

  return (
    <>
      <div
        ref={containerRef}
        className="w-full my-6 border border-[var(--doc-border)] bg-muted/5 rounded-xl overflow-hidden transition-all duration-500 animate-in fade-in slide-in-from-top-2"
      >
        <div className="py-3 px-5 border-b border-[var(--doc-border)] bg-muted/10 flex flex-row items-center justify-between group/html">
          <div className="flex flex-col">
            <h3 className="text-sm font-bold tracking-tight">
              {data.title || t("chat.artifact.htmlPreview", "HTML Preview")}
            </h3>
          </div>
          <div className="flex items-center gap-2 opacity-0 group-hover/html:opacity-100 transition-opacity">
            <Button
              variant="ghost"
              size="icon"
              className="h-8 w-8 rounded-full hover:bg-muted/50"
              onClick={handleCopy}
              title={t("common.copy")}
            >
              {copied ? (
                <Check className="w-4 h-4 text-green-500" />
              ) : (
                <Copy className="w-4 h-4 text-muted-foreground" />
              )}
            </Button>
            <Button
              variant="ghost"
              size="icon"
              className="h-8 w-8 rounded-full hover:bg-muted/50"
              onClick={handleOpenNewWindow}
              title={t("common.open")}
            >
              <ExternalLink className="w-4 h-4 text-muted-foreground" />
            </Button>
            <Button
              variant="ghost"
              size="icon"
              className="h-8 w-8 rounded-full hover:bg-muted/50"
              onClick={() => setIsFullscreen(true)}
              title={t("common.expand")}
            >
              <Maximize2 className="w-4 h-4 text-muted-foreground" />
            </Button>
          </div>
        </div>
        <div
          className="bg-white dark:bg-zinc-900 overflow-hidden relative flex items-center justify-center"
          style={{ height: `${data.height || 400}px` }}
        >
          {inView ? (
            <iframe
              title="HTML Preview"
              srcDoc={fullHtml}
              className="w-full h-full border-none"
              sandbox="allow-scripts allow-same-origin"
            />
          ) : (
            <span className="text-xs text-muted-foreground/40">
              {t("chat.artifact.scrollToPreview", "Scroll to preview")}
            </span>
          )}
        </div>
      </div>
      {renderFullscreenModal()}
    </>
  )
}
