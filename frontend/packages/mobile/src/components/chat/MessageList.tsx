import {
  AlertTriangle,
  ChevronDown,
  ChevronRight,
  Cpu,
  FileText,
  Loader2,
  Terminal,
  X,
  Search,
  ListTodo,
  HelpCircle,
  Bot,
  User,
  Brain,
  MoreHorizontal,
  Copy,
  Quote,
} from "lucide-react"
import { useEffect, useMemo, useRef, useState } from "react"
import { useTranslation } from "react-i18next"
import { Button } from "@evoloop/shared/components/ui/button"
import { Dialog, DialogContent, DialogTitle } from "@evoloop/shared/components/ui/dialog"
import { cn } from "@evoloop/shared"
import { Avatar, AvatarFallback, AvatarImage } from "@evoloop/shared/components/ui/avatar"
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@evoloop/shared/components/ui/dropdown-menu"
import { toast } from "sonner"
import { VList, VListHandle } from "virtua"
import { MobileHumanRequestCard } from "./MobileHumanRequestCard"
import type { LogMessage } from "../../hooks/useEvoLoopWebSocket"

function StarterButton({
  icon,
  label,
  desc,
  onClick,
}: {
  icon: React.ReactNode
  label: string
  desc: string
  onClick: () => void
}) {
  return (
    <Button
      variant="outline"
      className="h-auto py-3 px-3 justify-start gap-3 bg-muted/20 hover:bg-muted/40 border-border/40 rounded-xl"
      onClick={onClick}
    >
      <div className="p-2 bg-background rounded-lg shrink-0 shadow-sm border border-border/20">
        {icon}
      </div>
      <div className="flex flex-col items-start min-w-0 text-left">
        <span className="text-xs font-bold text-foreground truncate w-full">{label}</span>
        <span className="text-[10px] text-muted-foreground truncate w-full">{desc}</span>
      </div>
    </Button>
  )
}

function DateSeparator({ date }: { date: string }) {
  return (
    <div className="flex items-center gap-4 my-8 px-4 opacity-50">
      <div className="h-px bg-border flex-1" />
      <span className="text-[10px] font-bold text-muted-foreground uppercase tracking-widest bg-muted/50 px-2 py-0.5 rounded">
        {date}
      </span>
      <div className="h-px bg-border flex-1" />
    </div>
  )
}

interface MessageListProps {
  messages: LogMessage[]
  isProjectInitialized: boolean
  isDeviceOnline: boolean
  highlight: number | null
  onHITLResponse?: (threadId: string, response: string, commandId?: number) => void
  onStarterClick?: (text: string) => void
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

function RichContent({ content, className }: { content: any; className?: string }) {
  const { t } = useTranslation()
  const [viewerImage, setViewerImage] = useState<string | null>(null)

  if (typeof content !== "string") {
    return (
      <div className={cn("whitespace-pre-wrap", className)}>
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
    <div className={cn("text-sm leading-relaxed overflow-hidden", className)}>
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

function LogItem({
  msg,
  onHITLResponse,
  isGrouped,
  showAvatar
}: {
  msg: LogMessage;
  onHITLResponse?: (threadId: string, response: string, commandId?: number) => void;
  isGrouped?: boolean;
  showAvatar?: boolean;
}) {
  const { t } = useTranslation()
  const [isOpen, setIsOpen] = useState(false)

  const handleCopy = () => {
    navigator.clipboard.writeText(msg.content)
    toast.success(t("chat.interface.copied"))
  }

  const actions = (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button variant="ghost" size="icon" className="h-8 w-8 rounded-full opacity-0 group-hover:opacity-100 transition-opacity">
          <MoreHorizontal className="w-4 h-4" />
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align={msg.type === "user" ? "end" : "start"}>
        <DropdownMenuItem onClick={handleCopy}>
          <Copy className="mr-2 h-4 w-4" />
          {t("chat.interface.copy")}
        </DropdownMenuItem>
        <DropdownMenuItem>
          <Quote className="mr-2 h-4 w-4" />
          {t("chat.interface.quote")}
        </DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  )

  if (msg.type === "user") {
    return (
      <div className={cn(
        "flex justify-end gap-2 animate-in slide-in-from-right-2 fade-in duration-300 group",
        isGrouped ? "mb-1" : "mb-3"
      )}>
        <div className="flex flex-col items-end max-w-[85%] relative">
          <div className="bg-primary text-primary-foreground px-4 py-2.5 rounded-2xl rounded-tr-sm text-sm shadow-sm">
            <RichContent content={msg.content} />
          </div>
          <div className="absolute left-[-32px] top-1">
            {actions}
          </div>
        </div>
        <div className="w-8 shrink-0">
          {showAvatar && (
            <Avatar className="h-8 w-8">
              <AvatarFallback className="bg-primary/10 text-primary">
                <User size={16} />
              </AvatarFallback>
            </Avatar>
          )}
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
      <div className="mb-3 animate-in fade-in duration-300">
        <div className="flex items-center gap-2 text-[9px] text-muted-foreground mb-1 uppercase tracking-tighter font-bold opacity-70">
          <Terminal className="w-2.5 h-2.5" />
          <span>{t("chat.messageList.toolExecution")}</span>
        </div>
        <div className="bg-[#18181b] rounded-lg p-2.5 font-mono text-gray-300 overflow-x-auto shadow-sm border border-white/5 whitespace-pre-wrap leading-relaxed">
          <RichContent content={msg.content} className="text-[10px]" />
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

  // Default Output (Agent Response)
  let content = msg.content
  let thinking = null

  if (typeof content === "string") {
    const thinkMatch = content.match(/<think>([\s\S]*?)<\/think>/)
    if (thinkMatch) {
      thinking = thinkMatch[1].trim()
      content = content.replace(thinkMatch[0], "").trim()
    }
  }

  return (
    <div className={cn(
      "flex gap-3 animate-in slide-in-from-left-2 fade-in duration-300 group",
      isGrouped ? "mb-1" : "mb-4"
    )}>
      <div className="w-8 shrink-0 flex flex-col items-center">
        {(showAvatar && (msg.type === "ai" || !msg.type || (msg.type as any) === "hitl_request")) ? (
          <Avatar className="h-8 w-8">
            <AvatarImage src="/bot-avatar.png" />
            <AvatarFallback className="bg-muted text-muted-foreground">
              <Bot size={16} />
            </AvatarFallback>
          </Avatar>
        ) : (
          <div className="w-8" />
        )}
      </div>

      <div className="flex-1 flex flex-col max-w-[85%] relative">
        {thinking && (
          <div className="mb-2">
            <LogItem msg={{ ...msg, type: "thought", content: thinking }} isGrouped={false} showAvatar={false} />
          </div>
        )}

        {content && (
          <div className="bg-muted text-foreground px-4 py-3 rounded-2xl rounded-tl-sm text-sm shadow-sm border border-border/10">
            <RichContent content={content} />
          </div>
        )}
        <div className="absolute right-[-32px] top-1">
          {actions}
        </div>
      </div>
    </div>
  )
}

export function MessageList({
  messages,
  isProjectInitialized,
  isDeviceOnline,
  highlight,
  onHITLResponse,
  onStarterClick,
}: MessageListProps) {
  const { t } = useTranslation()
  const listRef = useRef<VListHandle>(null)
  const isAtBottomRef = useRef(true)

  // Desktop-style augmentation: Group by role + time, and add Daily Separators
  const augmentedMessages = useMemo(() => {
    const results: (LogMessage | { type: "date-separator"; date: string } | (LogMessage & { isRoleGrouped: boolean; showAvatar: boolean }))[] = []

    messages.forEach((msg, index) => {
      const prevMsg = messages[index - 1]

      // 1. Date Separator
      let showDate = false
      let dateString = ""
      if (msg.timestamp) {
        const d = new Date(msg.timestamp)
        dateString = d.toLocaleDateString(undefined, { weekday: 'short', month: 'short', day: 'numeric' })
        const prevDate = prevMsg?.timestamp ? new Date(prevMsg.timestamp).toLocaleDateString(undefined, { weekday: 'short', month: 'short', day: 'numeric' }) : null
        if (dateString !== prevDate) {
          showDate = true
        }
      }

      // 2. Grouping (Same Role, < 5 mins)
      // Note: 'thought' and 'tool' types are handled by the nested LogItem grouping in LogItem itself or via the 'type: group' logic below.
      // For general User/AI bubbles:
      const isRoleGrouped = prevMsg &&
        prevMsg.type === msg.type &&
        !showDate &&
        (["user", "ai"].includes(msg.type || "ai")) &&
        (msg.timestamp && prevMsg.timestamp ? (new Date(msg.timestamp).getTime() - new Date(prevMsg.timestamp).getTime() < 5 * 60 * 1000) : true)

      if (showDate) {
        results.push({ type: "date-separator", date: dateString })
      }

      results.push({
        ...msg,
        isRoleGrouped,
        showAvatar: !isRoleGrouped
      })
    })

    // 3. Post-process: Apply the collapsing group logic for tools/thoughts
    const finalGrouped: (LogMessage | { type: "date-separator"; date: string } | { type: "group"; groupType: "thought" | "tool"; items: LogMessage[] } | (LogMessage & { isRoleGrouped: boolean; showAvatar: boolean }))[] = []
    let currentGroup: LogMessage[] = []
    let currentGroupType: "thought" | "tool" | null = null

    results.forEach((msg) => {
      if (msg.type === "date-separator") {
        if (currentGroup.length > 0) {
          finalGrouped.push({ type: "group", groupType: currentGroupType!, items: [...currentGroup] })
          currentGroup = []
          currentGroupType = null
        }
        finalGrouped.push(msg)
        return
      }

      const isCollapsible = msg.type === "thought" || msg.type === "tool"
      if (isCollapsible) {
        if (currentGroupType && currentGroupType !== msg.type) {
          finalGrouped.push({ type: "group", groupType: currentGroupType, items: [...currentGroup] })
          currentGroup = [msg as LogMessage]
          currentGroupType = msg.type as "thought" | "tool"
        } else {
          currentGroup.push(msg as LogMessage)
          currentGroupType = msg.type as "thought" | "tool"
        }
      } else {
        if (currentGroup.length > 0) {
          finalGrouped.push({ type: "group", groupType: currentGroupType!, items: [...currentGroup] })
          currentGroup = []
          currentGroupType = null
        }
        finalGrouped.push(msg)
      }
    })

    if (currentGroup.length > 0) {
      finalGrouped.push({ type: "group", groupType: currentGroupType!, items: [...currentGroup] })
    }

    return finalGrouped
  }, [messages])

  // Auto-scroll logic for virtualization
  useEffect(() => {
    if (listRef.current && isAtBottomRef.current && !highlight) {
      listRef.current.scrollToIndex(augmentedMessages.length - 1, { align: "end" })
    }
  }, [augmentedMessages.length, highlight])

  useEffect(() => {
    if (highlight && listRef.current) {
      const index = augmentedMessages.findIndex(
        (m: any) => m.log_id === highlight || (m.items && m.items.some((i: any) => i.log_id === highlight))
      )
      if (index !== -1) {
        setTimeout(() => {
          listRef.current?.scrollToIndex(index, { align: "center" })
          // Highlight flash logic would need individual item tracking, 
          // but VList handles view well.
        }, 500)
      }
    }
  }, [highlight, augmentedMessages])

  if (!isProjectInitialized) {
    return (
      <div className="h-full flex-1 flex flex-col items-center justify-center p-8 text-center space-y-4">
        <Loader2 className="w-8 h-8 animate-spin text-muted-foreground" />
        <p className="text-sm text-muted-foreground">
          {t("chat.messageList.initializing")}
        </p>
      </div>
    )
  }

  if (messages.length === 0) {
    return (
      <div className="h-full flex-1 flex flex-col items-center justify-center p-6 text-center animate-in fade-in slide-in-from-bottom-4 duration-500">
        <Bot size={56} className="mb-4 opacity-10 text-primary" />
        <h2 className="text-xl font-bold text-foreground">
          {isDeviceOnline ? t("chat.interface.welcome", "How can I help you?") : t("chat.messageList.offline")}
        </h2>
        <p className="text-sm text-muted-foreground mt-1 mb-8 max-w-[240px]">
          {isDeviceOnline ? t("chat.interface.startPrompt", "I'm ready to manage your device or answer questions.") : t("chat.messageList.offlineDesc")}
        </p>

        {isDeviceOnline && (
          <div className="grid grid-cols-2 gap-3 w-full max-w-sm">
            <StarterButton
              icon={<Search className="text-blue-500" />}
              label={t("chat.context.starter.analyzeLabel", "Analyze")}
              desc={t("chat.context.starter.analyzeDesc", "Codebase architecture")}
              onClick={() => onStarterClick?.(t("chat.context.starter.analyze", "Analyze current codebase structure"))}
            />
            <StarterButton
              icon={<Brain className="text-purple-500" />}
              label={t("chat.context.starter.planLabel", "Plan")}
              desc={t("chat.context.starter.planDesc", "Draft roadmap")}
              onClick={() => onStarterClick?.(t("chat.context.starter.plan", "Create a new implementation plan"))}
            />
            <StarterButton
              icon={<ListTodo className="text-green-500" />}
              label={t("chat.context.starter.tasksLabel", "Tasks")}
              desc={t("chat.context.starter.tasksDesc", "Pending items")}
              onClick={() => onStarterClick?.(t("chat.context.starter.tasks", "What tasks are currently pending?"))}
            />
            <StarterButton
              icon={<HelpCircle className="text-amber-500" />}
              label={t("chat.context.starter.helpLabel", "Help")}
              desc={t("chat.context.starter.helpDesc", "Get guidance")}
              onClick={() => onStarterClick?.(t("chat.context.starter.help", "Help me understand this project"))}
            />
          </div>
        )}
      </div>
    )
  }

  return (
    <div className="flex-1 overflow-hidden relative">
      <VList
        ref={listRef}
        className="h-full p-4"
        onScroll={(offset) => {
          if (!listRef.current) return
          // virtua VList doesn't have virtualSize directly on handle, 
          // we use the scrollSize and viewport size from the container if needed,
          // but virtua handles most of this. For auto-scroll we use offset.
          const isAtBottom = offset + (listRef.current as any).viewportSize >= (listRef.current as any).scrollSize - 50
          isAtBottomRef.current = isAtBottom
        }}
      >
        {augmentedMessages.map((item: any, i) => {
          if (item.type === "date-separator") {
            return <DateSeparator key={`date-${i}`} date={item.date} />
          }
          if (item.type === "group") {
            if (item.groupType === "thought") {
              return (
                <div key={`thought-group-${i}`} className="mb-4">
                  <ThoughtGroup items={item.items} />
                </div>
              )
            } else if (item.groupType === "tool") {
              return (
                <div key={`tool-group-${i}`} className="mb-4">
                  <ToolGroup items={item.items} />
                </div>
              )
            }
          }
          return (
            <div
              key={item.log_id || i}
              id={item.log_id ? `log-${item.log_id}` : undefined}
            >
              <LogItem
                msg={item}
                onHITLResponse={onHITLResponse}
                isGrouped={item.isRoleGrouped}
                showAvatar={item.showAvatar}
              />
            </div>
          )
        })}
      </VList>

      {!isAtBottomRef.current && messages.length > 5 && (
        <Button
          size="icon"
          variant="secondary"
          className="absolute bottom-4 right-4 rounded-full shadow-lg opacity-90 animate-in fade-in slide-in-from-bottom-2"
          onClick={() => {
            isAtBottomRef.current = true
            listRef.current?.scrollToIndex(augmentedMessages.length - 1, {
              align: "end",
              smooth: true,
            })
          }}
        >
          <ChevronDown className="w-5 h-5" />
        </Button>
      )}
    </div>
  )
}

function ThoughtGroup({ items }: { items: LogMessage[] }) {
  const { t } = useTranslation()
  const [isOpen, setIsOpen] = useState(false)

  return (
    <div className="mb-3 animate-in fade-in duration-300 border-l-2 border-primary/20 ml-1 pl-3">
      <button
        onClick={() => setIsOpen(!isOpen)}
        className="flex items-center gap-2 text-[10px] font-medium text-muted-foreground hover:text-foreground transition-colors w-full py-1"
      >
        {isOpen ? (
          <ChevronDown className="w-3 h-3" />
        ) : (
          <ChevronRight className="w-3 h-3" />
        )}
        <Cpu className="w-3 h-3" />
        <span>
          {t("chat.messageList.agentThought")} ({items.length})
        </span>
      </button>
      {isOpen && (
        <div className="space-y-4 pt-2">
          {items.map((item, idx) => (
            <div key={idx} className="text-xs font-mono text-muted-foreground bg-muted/20 p-2.5 rounded-md leading-relaxed border border-border/10">
              {item.content}
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
function ToolGroup({ items }: { items: LogMessage[] }) {
  const { t } = useTranslation()
  const [isOpen, setIsOpen] = useState(false)

  // Show last item content as a preview if collapsed
  return (
    <div className="mb-3 animate-in fade-in duration-300">
      <button
        onClick={() => setIsOpen(!isOpen)}
        className="flex items-center gap-2 text-[10px] font-medium text-muted-foreground hover:text-foreground transition-colors w-full py-1 h-9 bg-muted/30 px-3 rounded-lg border border-border/10 shadow-sm"
      >
        <div className="flex items-center justify-center w-5 h-5 rounded-full bg-primary/10 mr-1">
          {isOpen ? (
            <ChevronDown className="w-3 h-3 text-primary" />
          ) : (
            <ChevronRight className="w-3 h-3 text-primary" />
          )}
        </div>
        <Terminal className="w-3.5 h-3.5" />
        <span className="flex-1 text-left font-semibold">
          {t("chat.messageList.toolExecution")}
          <span className="ml-1.5 opacity-50 font-normal">({items.length})</span>
        </span>
        {!isOpen && items.length > 0 && (
          <span className="text-[9px] font-mono opacity-40 truncate max-w-[120px] bg-black/20 px-1.5 py-0.5 rounded">
            {items[items.length - 1].content.toString().substring(0, 20)}...
          </span>
        )}
      </button>
      {isOpen && (
        <div className="mt-2 space-y-1 pl-4 border-l-2 border-primary/10 ml-2.5 py-1">
          {items.map((item, idx) => (
            <LogItem key={idx} msg={item} />
          ))}
        </div>
      )}
    </div>
  )
}
