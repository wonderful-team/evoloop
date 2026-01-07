import { FileText, X } from "lucide-react"
import { useState } from "react"
import { useTranslation } from "react-i18next"
import ReactMarkdown from "react-markdown"
import { Prism as SyntaxHighlighter } from "react-syntax-highlighter"
import { vscDarkPlus } from "react-syntax-highlighter/dist/esm/styles/prism"
import remarkGfm from "remark-gfm"
import { Button } from "@/components/ui/button"
import { Dialog, DialogContent, DialogTitle } from "@/components/ui/dialog"

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
            alt="Full view"
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

export function MessageContent({ content }: { content: string }) {
  const { t } = useTranslation()
  const [viewerImage, setViewerImage] = useState<string | null>(null)

  if (typeof content !== "string") {
    return (
      <div className="whitespace-pre-wrap">
        {JSON.stringify(content, null, 2)}
      </div>
    )
  }

  // Split by [Image: ...] or [File: ...]
  // Fix: Regex now accepts any non-bracket characters as URL/Path to support local refs
  const parts = content.split(/(\[(?:Image|File):\s*[^\]]+\])/g)

  const handleFileClick = (url: string) => {
    window.open(url, "_blank")
  }

  return (
    <div className="text-sm leading-relaxed overflow-hidden break-words">
      {parts.map((part, index) => {
        const imageMatch = part.match(/^\[Image:\s*([^\]]+)\]$/)
        const fileMatch = part.match(/^\[File:\s*([^\]]+)\]$/)

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

        // Render Markdown for text parts
        if (!part) return null

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

                if (!inline && match) {
                  const codeBlock = (
                    <div className="my-2 rounded-md overflow-hidden bg-[#1e1e1e]">
                      <div className="flex items-center justify-between px-3 py-1 bg-[#252526] text-[10px] text-gray-400 border-b border-[#3e3e3e]">
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
              // Style other elements
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
                  className="text-primary underline underline-offset-4 hover:opacity-80 break-all"
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
                <th className="bg-muted px-4 py-2 font-medium border-b">
                  {children}
                </th>
              ),
              td: ({ children }) => (
                <td className="px-4 py-2 border-b last:border-0">{children}</td>
              ),
              img: ({ src, alt }) => (
                <img
                  src={src}
                  alt={alt}
                  className="max-w-full rounded-lg my-2"
                />
              ),
              li: ({ children }) => {
                // Check if children (text) starts with our tool emojis
                const text = String(children)
                const isToolAction = /^(📄|📝|💻|📅|🔍|🔧|📁|📍)/.test(text)

                if (isToolAction) {
                  // Style as a chip/badge
                  // Distinct colors for different actions could be nice, but uniform "Action" look is also clean.
                  // Let's use a subtle border and background.
                  return (
                    <li className="list-none mb-1.5 last:mb-0">
                      <span className="inline-flex items-center px-2.5 py-1 rounded-md bg-muted/50 border border-border text-xs font-medium font-mono text-muted-foreground hover:text-foreground hover:bg-muted transition-colors">
                        {children}
                      </span>
                    </li>
                  )
                }

                return <li className="mb-0.5">{children}</li>
              },
            }}
          >
            {part}
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
