import {
  AlertTriangle,
  ChevronDown,
  ChevronRight,
  Cpu,
  FileText,
  Loader2,
  Terminal,
  X,
} from "lucide-react"
import { useEffect, useRef, useState } from "react"
import { useTranslation } from "react-i18next"
import { Button } from "@/components/ui/button"
import { Dialog, DialogContent, DialogTitle } from "@/components/ui/dialog"
import { MobileHumanRequestCard } from "./MobileHumanRequestCard"
import type { LogMessage } from "@/hooks/useEvoLoopWebSocket"

interface MessageListProps {
  messages: LogMessage[]
  isProjectInitialized: boolean
  isDeviceOnline: boolean
  highlight: number | null
  onHITLResponse?: (threadId: string, response: string, commandId?: number) => void
}

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

import ReactMarkdown from "react-markdown"
import { Prism as SyntaxHighlighter } from "react-syntax-highlighter"
import { vscDarkPlus } from "react-syntax-highlighter/dist/esm/styles/prism"
import remarkGfm from "remark-gfm"

function RichContent({ content }: { content: any }) {
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
  const parts = content.split(/(\[(?:Image|File):\s*https?:\/\/[^\]]+\])/g)

  const handleFileClick = (url: string) => {
    window.open(url, "_blank")
  }

  return (
    <div className="text-sm leading-relaxed overflow-hidden">
      {parts.map((part, index) => {
        const imageMatch = part.match(/^\[Image:\s*(https?:\/\/[^\]]+)\]$/)
        const fileMatch = part.match(/^\[File:\s*(https?:\/\/[^\]]+)\]$/)

        if (imageMatch) {
          const url = imageMatch[1]
          return (
            <div key={index} className="my-2">
              <img
                src={url}
                alt="User upload"
                className="max-w-[200px] max-h-[200px] rounded-lg border bg-muted object-cover cursor-zoom-in hover:brightness-90 transition-all"
                onClick={() => setViewerImage(url)}
              />
            </div>
          )
        }

        if (fileMatch) {
          const url = fileMatch[1]
          const filename = url.split("/").pop() || "File"
          return (
            <div
              key={index}
              className="my-2 inline-flex items-center gap-2 p-3 bg-muted/50 border rounded-lg cursor-pointer hover:bg-muted transition-colors max-w-full"
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
            </div>
          )
        }

        // Render Markdown for text parts
        // Handle empty or whitespace-only parts gracefully if needed, but Markdown handles them fine.
        if (!part) return null

        return (
          <ReactMarkdown
            key={index}
            remarkPlugins={[remarkGfm]}
            components={{
              code({ node, inline, className, children, ...props }: any) {
                const match = /language-(\w+)/.exec(className || "")
                return !inline && match ? (
                  <div className="my-2 rounded-md overflow-hidden bg-[#1e1e1e]">
                    <div className="flex items-center justify-between px-3 py-1 bg-[#252526] text-[10px] text-gray-400 border-b border-[#3e3e3e]">
                      <span>{match[1]}</span>
                      <button
                        onClick={() =>
                          navigator.clipboard.writeText(String(children))
                        }
                        className="hover:text-white transition-colors"
                      >
                        {t("chat.messageList.copy")}
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
                      }}
                      {...props}
                    >
                      {String(children).replace(/\n$/, "")}
                    </SyntaxHighlighter>
                  </div>
                ) : (
                  <code
                    className="bg-muted px-1.5 py-0.5 rounded text-[85%] font-mono"
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

function LogItem({ msg, onHITLResponse }: { msg: LogMessage; onHITLResponse?: (threadId: string, response: string, commandId?: number) => void }) {
  const { t } = useTranslation()
  const [isOpen, setIsOpen] = useState(false)

  if (msg.type === "user") {
    return (
      <div className="flex justify-end mb-4 animate-in slide-in-from-right-2 fade-in duration-300">
        <div className="bg-primary text-primary-foreground px-4 py-2 rounded-2xl rounded-tr-sm max-w-[85%] text-sm shadow-sm">
          <RichContent content={msg.content} />
        </div>
      </div>
    )
  }

  if (msg.type === "thought") {
    return (
      <div className="mb-3 animate-in fade-in duration-300">
        <button
          onClick={() => setIsOpen(!isOpen)}
          className="flex items-center gap-2 text-xs font-medium text-muted-foreground hover:text-foreground transition-colors w-full mb-1"
        >
          {isOpen ? (
            <ChevronDown className="w-3 h-3" />
          ) : (
            <ChevronRight className="w-3 h-3" />
          )}
          <Cpu className="w-3 h-3" />
          {t("chat.messageList.agentThought")}
        </button>
        {isOpen && (
          <div className="ml-2 pl-3 border-l-2 border-primary/20 text-xs font-mono text-muted-foreground bg-muted/30 p-2 rounded-r-md">
            {msg.content}
          </div>
        )}
      </div>
    )
  }

  if (msg.type === "tool") {
    return (
      <div className="mb-3 ml-2 pl-3 border-l-2 border-muted-foreground/30 animate-in fade-in duration-300">
        <div className="flex items-center gap-2 text-xs text-muted-foreground mb-1">
          <Terminal className="w-3 h-3" />
          <span>{t("chat.messageList.toolExecution")}</span>
        </div>
        <div className="bg-muted rounded-md p-2 text-xs font-mono text-muted-foreground overflow-x-auto">
          <RichContent content={msg.content} />
        </div>
      </div>
    )
  }

  if (msg.type === "error") {
    return (
      <div className="flex gap-2 mb-3 p-3 bg-destructive/10 rounded-lg text-sm text-destructive border-l-4 border-destructive animate-in shake">
        <AlertTriangle className="w-4 h-4 mt-0.5 shrink-0" />
        <div className="break-words">{msg.content}</div>
      </div>
    )
  }

  if (msg.type === "hitl_request") {
    // Content should be object, but check type
    const requestData = typeof msg.content === "string" ? JSON.parse(msg.content) : msg.content

    return (
      <div className="flex flex-col mb-4 animate-in slide-in-from-left-2 fade-in duration-300 max-w-[95%]">
        {/* HITL Card */}
        <MobileHumanRequestCard
          request={requestData}
          onRespond={(response) => {
            if (onHITLResponse && msg.thread_id) {
              onHITLResponse(msg.thread_id, response, msg.log_id)
            }
          }}
        />
      </div>
    )
  }

  // Default Output (Agent Response or General Info)
  let content = msg.content
  let thinking = null

  // Parse Thinking from content string
  if (typeof content === "string") {
    const thinkMatch = content.match(/<think>([\s\S]*?)<\/think>/)
    if (thinkMatch) {
      thinking = thinkMatch[1].trim()
      content = content.replace(thinkMatch[0], "").trim()
    }
  }

  return (
    <div className="flex flex-col mb-4 animate-in slide-in-from-left-2 fade-in duration-300 max-w-[85%]">
      {/* Thinking Block (Extracted) */}
      {thinking && (
        <div className="mb-2">
          <LogItem msg={{ ...msg, type: "thought", content: thinking }} />
        </div>
      )}

      {/* Main Content */}
      <div className="bg-card border border-border text-card-foreground px-4 py-3 rounded-2xl rounded-tl-sm text-sm shadow-sm">
        <RichContent content={content} />
      </div>
    </div>
  )
}

export function MessageList({
  messages,
  isProjectInitialized,
  isDeviceOnline,
  highlight,
  onHITLResponse
}: MessageListProps) {
  const { t } = useTranslation()
  const scrollRef = useRef<HTMLDivElement>(null)

  // Auto-scroll
  useEffect(() => {
    if (scrollRef.current && !highlight) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight
    }
  }, [highlight])

  useEffect(() => {
    if (highlight) {
      setTimeout(() => {
        const element = document.getElementById(`log-${highlight}`)
        if (element) {
          element.scrollIntoView({ behavior: "smooth", block: "center" })
          element.classList.add("bg-primary/20")
          setTimeout(() => element.classList.remove("bg-primary/20"), 2000)
        }
      }, 500)
    }
  }, [highlight]) // Trigger when messages load

  return (
    <div className="flex-1 overflow-y-auto p-4 scroll-smooth" ref={scrollRef}>
      {!isProjectInitialized ? (
        <div className="h-full flex flex-col items-center justify-center p-8 text-center space-y-4">
          <Loader2 className="w-8 h-8 animate-spin text-muted-foreground" />
          <p className="text-sm text-muted-foreground">
            {t("chat.messageList.initializing")}
          </p>
        </div>
      ) : messages.length === 0 ? (
        <div className="h-full flex flex-col items-center justify-center p-8 text-center space-y-4">
          <div
            className={`w-16 h-16 rounded-full flex items-center justify-center transition-colors ${isDeviceOnline ? "bg-muted" : "bg-red-50"}`}
          >
            {isDeviceOnline ? (
              <Terminal className="w-8 h-8 text-muted-foreground" />
            ) : (
              <AlertTriangle className="w-8 h-8 text-red-300" />
            )}
          </div>
          <div className="space-y-2">
            <h3 className="font-semibold text-foreground">
              {isDeviceOnline
                ? t("chat.messageList.ready")
                : t("chat.messageList.offline")}
            </h3>
            <p className="text-sm text-muted-foreground max-w-[200px]">
              {isDeviceOnline
                ? t("chat.messageList.readyDesc")
                : t("chat.messageList.offlineDesc")}
            </p>
          </div>
        </div>
      ) : (
        messages.map((msg, i) => (
          <div id={msg.log_id ? `log-${msg.log_id}` : undefined} key={i}>
            <LogItem msg={msg} onHITLResponse={onHITLResponse} />
          </div>
        ))
      )}
    </div>
  )
}
