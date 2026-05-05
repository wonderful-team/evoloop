import { FileText, X, Music } from "lucide-react"
import { useState } from "react"
import { useTranslation } from "react-i18next"
import ReactMarkdown from "react-markdown"
import { Prism as SyntaxHighlighter } from "react-syntax-highlighter"
import { vscDarkPlus } from "react-syntax-highlighter/dist/esm/styles/prism"
import remarkGfm from "remark-gfm"
import { Button } from "@evoloop/shared/components/ui/button"
import { Dialog, DialogContent, DialogTitle } from "@evoloop/shared/components/ui/dialog"
import { Mermaid } from "@/components/Common/Mermaid"

function ImageViewer({
  src,
  isOpen,
  onClose,
}: {
  src: string
  isOpen: boolean
  onClose: () => void
}) {
  const { t } = useTranslation()
  if (!isOpen) return null
  return (
    <Dialog open={isOpen} onOpenChange={onClose}>
      <DialogContent className="max-w-full h-full p-0 bg-black/90 border-none sm:rounded-none flex flex-col justify-center items-center">
        <DialogTitle className="sr-only">
          {t("chat.messageList.imageViewer")}
        </DialogTitle>
        <div className="relative w-full h-full flex items-center justify-center p-2">
          <img
            src={src}
            alt={t("common.fullView")}
            className="max-w-full max-h-full object-contain"
          />
          <Button
            variant="ghost"
            size="icon"
            className="absolute top-4 right-4 text-white/70 hover:text-white hover:bg-white/20 rounded-full"
            onClick={onClose}
          >
            <X className="w-6 h-6" />
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  )
}

export function MessageContent({ content, isUser }: { content: string; isUser?: boolean }) {
  const { t } = useTranslation()
  const [viewerImage, setViewerImage] = useState<string | null>(null)

  if (typeof content !== "string") {
    return (
      <div className="whitespace-pre-wrap text-xs font-mono opacity-60">
        {JSON.stringify(content, null, 2)}
      </div>
    )
  }

  // 0. Pre-process: Filter out technical XML tags (audit, report, thought, etc.)
  // This is a safety net for streaming and database markers.
  let displayContent = content;

  // A. If <report> exists, prioritize its content as the main message
  const reportMatch = displayContent.match(/<report>([\s\S]*?)(?:<\/report>|$)/i);
  if (reportMatch) {
    displayContent = reportMatch[1].trim();
  } else {
    // B. Hide internal audit tags and their content
    displayContent = displayContent
      .replace(/<audit>[\s\S]*?(?:<\/audit>|$)/gi, "")
      .replace(/<outcome>[\s\S]*?(?:<\/outcome>|$)/gi, "")
      .replace(/<reason>[\s\S]*?(?:<\/reason>|$)/gi, "")
      .replace(/<proof_points>[\s\S]*?(?:<\/proof_points>|$)/gi, "");
    
    // C. Peel any remaining report tags (e.g. if partial)
    displayContent = displayContent.replace(/<\/?report>/gi, "");
  }

  // Clean up extra whitespace/newlines caused by stripping
  displayContent = displayContent.trim();

  // Split by [Image: ...], [File: ...], or [Audio: ...](url)
  const parts = displayContent.split(/(\[(?:Image|File|Audio):\s*[^\]]+\]\([^)]+\)|\[(?:Image|File|Audio):\s*[^\]]+\])/g)

  const handleFileClick = (url: string) => {
    window.open(url, "_blank")
  }

  return (
    <div className="leading-relaxed w-full max-w-full overflow-hidden break-words">
      {parts.map((part, index) => {
        const imageMatch = part.match(/^\[Image:\s*([^\]]+)\]$/)
        const fileMatch = part.match(/^\[File:\s*([^\]]+)\]$/)
        // Audio format: [Audio: name](url) or [Audio: url]
        const audioMatch = part.match(/^\[Audio:\s*([^\]]+)\](?:\(([^)]+)\))?$/)

        if (imageMatch) {
          const url = imageMatch[1]
          return (
            <div key={index} className="my-2">
              <button
                type="button"
                className="block max-w-[300px] max-h-[300px] rounded-lg border bg-muted overflow-hidden cursor-zoom-in hover:brightness-90 transition-all"
                onClick={() => setViewerImage(url)}
              >
                <img
                  src={url}
                  alt="User upload"
                  className="w-full h-full object-cover"
                />
              </button>
            </div>
          )
        }

        if (fileMatch) {
          const url = fileMatch[1]
          const filename = url.split("/").pop() || "File"
          return (
            <button
              key={index}
              type="button"
              className="my-2 inline-flex items-center gap-2 p-3 bg-muted/50 border rounded-lg cursor-pointer hover:bg-muted transition-colors max-w-full text-left"
              onClick={() => handleFileClick(url)}
            >
              <div className="bg-primary/10 p-2 rounded-md">
                <FileText className="w-5 h-5 text-primary" />
              </div>
              <div className="flex flex-col overflow-hidden">
                <span className="text-sm font-medium truncate">
                  {decodeURIComponent(filename)}
                </span>
                <span className="text-xs text-muted-foreground uppercase">
                  {t("chat.messageList.clickToOpen")}
                </span>
              </div>
            </button>
          )
        }

        if (audioMatch) {
          const name = audioMatch[1]
          const url = audioMatch[2] || audioMatch[1] // fallback to name if no url group
          return (
            <div key={index} className="my-2">
              <div className="inline-flex items-center gap-3 p-3 bg-amber-500/10 border border-amber-500/20 rounded-lg max-w-full">
                <div className="bg-amber-500/20 p-2 rounded-md shrink-0">
                  <Music className="w-5 h-5 text-amber-600 dark:text-amber-400" />
                </div>
                <div className="flex flex-col min-w-0">
                  <span className="text-sm font-medium text-amber-800 dark:text-amber-200 truncate">
                    {name}
                  </span>
                  <audio
                    controls
                    src={url}
                    className="h-8 w-[200px] sm:w-[250px] mt-1"
                    preload="metadata"
                  >
                    {t("chat.messageList.audioNotSupported", "Your browser does not support audio playback")}
                  </audio>
                </div>
              </div>
            </div>
          )
        }

        // Render Markdown for text parts
        if (!part) return null

        // Fix for aggressive auto-linking: Wrap URLs in < > if they are inside parentheses
        const processedPart = part.replace(/(\()(https?:\/\/[^\s)]+)(\))/g, "$1<$2>$3")

        return (
          <ReactMarkdown
            key={index}
            remarkPlugins={[remarkGfm]}
            components={{
              code({ node, inline, className, children, ...props }: any) {
                const match = /language-(\w+)/.exec(className || "")
                const codeString = String(children).replace(/\n$/, "")
                const lineCount = codeString.split("\n").length
                const isLong = lineCount > 15

                // Support for Mermaid diagrams
                if (!inline && match && match[1] === "mermaid") {
                  return <Mermaid chart={codeString} />
                }

                if (!inline && match) {
                  const codeBlock = (
                    <div className="my-2 rounded-md overflow-hidden bg-[#1e1e1e] border border-[#3e3e3e] max-w-full">
                      <div className="flex items-center justify-between px-3 py-1 bg-[#252526] text-[10px] text-gray-400 border-b border-[#3e3e3e] w-full overflow-hidden">
                        <span>
                          {match[1]} {isLong && `(${lineCount} lines)`}
                        </span>
                        <button
                          type="button"
                          onClick={() =>
                            navigator.clipboard.writeText(codeString)
                          }
                          className="hover:text-white transition-colors"
                        >
                          {t("chat.messageList.copy", "Copy")}
                        </button>
                      </div>
                      <SyntaxHighlighter
                        style={vscDarkPlus as any}
                        language={match[1]}
                        PreTag="div"
                        customStyle={{
                          margin: 0,
                          borderRadius: 0,
                          fontSize: "12px",
                          maxHeight: isLong ? "200px" : "none",
                          overflow: "auto",
                        }}
                        {...props}
                      >
                        {codeString}
                      </SyntaxHighlighter>
                    </div>
                  )
                  return codeBlock
                }

                return (
                  <code
                    className="bg-muted px-1.5 py-0.5 rounded text-[85%] font-mono break-all"
                    {...props}
                  >
                    {children}
                  </code>
                )
              },
              p: ({ children }) => <p className="mb-2 last:mb-0">{children}</p>,
              ul: ({ children }) => (
                <ul className="list-disc pl-4 mb-2 space-y-1">{children}</ul>
              ),
              ol: ({ children }) => (
                <ol className="list-decimal pl-4 mb-2 space-y-1">{children}</ol>
              ),
              a: ({ href, children }) => (
                <a
                  href={href}
                  target="_blank"
                  rel="noopener noreferrer"
                  className={`${isUser ? "text-inherit" : "text-primary"} underline underline-offset-4 hover:opacity-80 break-all`}
                >
                  {children}
                </a>
              ),
              blockquote: ({ children }) => (
                <blockquote className="border-l-4 border-primary/30 pl-3 italic text-muted-foreground my-2">
                  {children}
                </blockquote>
              ),
              table: ({ children }) => (
                <div className="overflow-x-auto my-2 rounded-lg border">
                  <table className="w-full text-sm text-left">{children}</table>
                </div>
              ),
              th: ({ children }) => (
                <th className="bg-muted px-4 py-2 font-medium border-b border-r last:border-r-0">
                  {children}
                </th>
              ),
              td: ({ children }) => (
                <td className="px-4 py-2 border-b border-r last:border-r-0">{children}</td>
              ),
              img: ({ src, alt }) => (
                <img
                  src={src}
                  alt={alt}
                  className="max-w-full rounded-lg my-2"
                />
              ),
              li: ({ children }) => <li className="mb-0.5">{children}</li>,
            }}
          >
            {processedPart}
          </ReactMarkdown>
        )
      })}

      <ImageViewer
        isOpen={!!viewerImage}
        src={viewerImage || ""}
        onClose={() => setViewerImage(null)}
      />
    </div>
  )
}
