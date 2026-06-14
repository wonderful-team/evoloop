import { FileText, X, Music, Loader2 } from "lucide-react"
import { memo, useState, useRef, useCallback, useDeferredValue } from "react"
import { useTranslation } from "react-i18next"
import ReactMarkdown from "react-markdown"
// TEMP: syntax-highlighter disabled for performance profiling
import remarkGfm from "remark-gfm"
import { Button } from "@evoloop/shared/components/ui/button"
import { Dialog, DialogContent, DialogTitle } from "@evoloop/shared/components/ui/dialog"
import { Mermaid } from "@/components/Common/Mermaid"
import { extractArtifactsFromContent } from "./Artifacts/utils"
import { MessageReferences } from "./MessageReferences"
import { EChartsArtifact } from "./Artifacts/EChartsArtifact"
import { ChangesetSnapshot } from "./ChangesetSnapshotView"
import { CodeBlock } from "./CodeBlock"

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

interface MessageContentProps {
  content: string
  isUser?: boolean
}

export const MessageContent = memo(({ content, isUser }: MessageContentProps) => {
  const { t } = useTranslation()
  const deferredContent = useDeferredValue(content)
  const [viewerImage, setViewerImage] = useState<string | null>(null)
  const [previewHtml, setPreviewHtml] = useState<string | null>(null)

  // Cache for successfully parsed code-block artifacts (ECharts, etc.)
  // Key: stable hash string from code content. Value: frozen parsed option.
  // This prevents re-parsing (and re-mounting) charts while SSE is still streaming
  // text that comes AFTER the chart block.
  const parsedCodeCache = useRef<Map<string, any>>(new Map())

  // Stable hash for a code string: length + first 80 chars is sufficient
  // to uniquely identify a complete ECharts JSON block.
  const cacheKey = useCallback((code: string) => `${code.length}:${code.slice(0, 80)}`, [])

  if (!deferredContent) return null

  // 0. Pre-process: Filter out technical XML tags (audit, report, thought, etc.)
  let displayContent = deferredContent;

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

  displayContent = displayContent.trim();

  // 1. Extract artifacts
  const artifactParts = extractArtifactsFromContent(displayContent)

  const handleFileClick = (url: string) => {
    window.open(url, "_blank")
  }

  return (
    <div className="leading-relaxed w-full max-w-full overflow-hidden break-words [word-break:break-word] flex flex-col gap-2">
      {artifactParts.map((part, pIdx) => {
        if (part.type === 'artifact') {
          const artifactRef = {
            id: `inline-${pIdx}`,
            type: 'artifact' as const,
            target_id: 'inline',
            target_name: part.artifactType || 'Artifact',
            meta_data: {
              artifact_type: part.artifactType,
              data: part.data
            }
          }
          return <MessageReferences key={pIdx} references={[artifactRef]} />
        }

        // Handle text part: split by legacy resource tags
        const textContent = part.content || ""
        if (!textContent) return null

        const subParts = textContent.split(/(\[(?:Image|File|Audio):\s*[^\]]+\]\([^)]+\)|\[(?:Image|File|Audio):\s*[^\]]+\])/g)

        return (
          <div key={pIdx} className="flex flex-col gap-2">
            {subParts.map((subPart, index) => {
              const imageMatch = subPart.match(/^\[Image:\s*([^\]]+)\]$/)
              const fileMatch = subPart.match(/^\[File:\s*([^\]]+)\]$/)
              const audioMatch = subPart.match(/^\[Audio:\s*([^\]]+)\](?:\(([^)]+)\))?$/)

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
                const url = audioMatch[2] || audioMatch[1]
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
              if (!subPart) return null
              const processedPart = subPart.replace(/(\()(https?:\/\/[^\s)]+)(\))/g, "$1<$2>$3")

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

                      if (!inline && match && match[1] === "mermaid") {
                        return <Mermaid chart={codeString} />
                      }

                      if (!inline && match && match[1] === "echarts") {
                        try {
                          const ck = cacheKey(codeString)
                          let option = parsedCodeCache.current.get(ck)
                          if (!option) {
                            const parsed = JSON.parse(codeString)
                            // Accept any valid ECharts option object (series, dataset, etc.)
                            if (parsed && typeof parsed === 'object' && !Array.isArray(parsed)) {
                              // Do NOT freeze — ECharts mutates the option internally during layout processing.
                              // The ref-based cache already provides a stable reference for React.memo.
                              option = parsed
                              parsedCodeCache.current.set(ck, option)
                            }
                          }
                          if (option) {
                            return <EChartsArtifact key={ck} data={{ option }} />
                          }
                        } catch {
                          // incomplete JSON during streaming
                          return (
                            <div className="my-2 p-6 bg-muted/30 rounded-lg border border-dashed flex flex-col items-center justify-center text-sm text-muted-foreground">
                              <Loader2 className="w-6 h-6 mb-2 animate-spin text-primary/50" />
                              <span>{t("chat.artifact.generatingChart", "Generating Chart...")}</span>
                              <span className="text-xs opacity-50 mt-1">{codeString.length} bytes received</span>
                            </div>
                          )
                        }
                      }

                      if (!inline && match && match[1] === "html") {
                        return <CodeBlock language="html" codeString={codeString} isLong={isLong} lineCount={lineCount} onPreview={setPreviewHtml} />
                      }

                      if (!inline && match && match[1] === "json") {
                        try {
                          const jsonObj = JSON.parse(codeString)
                          if (jsonObj && typeof jsonObj === "object" && jsonObj.type === "changeset") {
                            // Map agent changeset format to ChangesetSnapshotView format
                            const files = (jsonObj.changes || []).map((c: any) => {
                              let op = 'modified'
                              if (c.op === 'ADD') op = 'added'
                              else if (c.op === 'DELETE') op = 'deleted'
                              else if (c.op === 'RENAME') op = 'renamed'
                              return { path: c.path || c.file || '', operation: op }
                            })
                            return (
                              <ChangesetSnapshot 
                                files={files} 
                                totalCount={files.length} 
                                onViewDetails={(path) => console.log('View details', path)} 
                              />
                            )
                          }
                        } catch (e) {
                          // Fallback to normal rendering if JSON is invalid
                        }
                      }

                      if (!inline && match) {
                        const lang = match[1] === "markdown" ? "text" : match[1]
                        return <CodeBlock language={lang} codeString={codeString} isLong={isLong} lineCount={lineCount} />
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
                    ul: ({ children }) => <ul className="list-disc pl-4 mb-2 space-y-1">{children}</ul>,
                    ol: ({ children }) => <ol className="list-decimal pl-4 mb-2 space-y-1">{children}</ol>,
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
                    td: ({ children }) => <td className="px-4 py-2 border-b border-r last:border-r-0">{children}</td>,
                    img: ({ src, alt }) => src ? <img src={src} alt={alt} className="max-w-full rounded-lg my-2" /> : null,
                    li: ({ children }) => <li className="mb-0.5">{children}</li>,
                    hr: () => <hr className="my-2 border-border/30" />,
                  }}
                >
                  {processedPart}
                </ReactMarkdown>
              )
            })}
          </div>
        )
      })}

      <ImageViewer
        src={viewerImage || ""}
        isOpen={!!viewerImage}
        onClose={() => setViewerImage(null)}
      />

      <Dialog open={!!previewHtml} onOpenChange={() => setPreviewHtml(null)}>
        <DialogContent className="max-w-full sm:max-w-full h-full p-0 bg-black/90 border-none sm:rounded-none flex flex-col">
          <DialogTitle className="sr-only">
            {t("chat.artifact.htmlPreview", "HTML Preview")}
          </DialogTitle>
          <div className="relative w-full h-full flex-1">
            <iframe
              srcDoc={previewHtml || ""}
              className="w-full h-full border-none"
              sandbox="allow-scripts"
            />
          </div>
        </DialogContent>
      </Dialog>
    </div>
  )
})
