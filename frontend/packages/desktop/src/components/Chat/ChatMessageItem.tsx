import { memo, useEffect } from "react"
import { motion } from "framer-motion"
import {
  Bot, User, Copy, RotateCcw, Undo, MoreHorizontal,
  Brain, Quote, ChevronRight, Loader2
} from "lucide-react"
import { useTranslation } from "react-i18next"
import { toast } from "sonner"
import { Button } from "@evoloop/shared/components/ui/button"
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger
} from "@evoloop/shared/components/ui/dropdown-menu"
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger
} from "@evoloop/shared/components/ui/collapsible"
import { Badge } from "@evoloop/shared/components/ui/badge"
import { cn } from "@evoloop/shared/lib/utils"
import { MessageContent } from "./MessageContent"
import { ChangesetSnapshot } from "./ChangesetSnapshotView"
import { TTSButton } from "./TTSButton"
import { useTTS, useAutoSpeak } from "@/hooks/useTTS"
import { useAuth } from "@/hooks/useAuth"
import { useSystemConfig } from "@/hooks/useSystemConfig"

export interface Message {
  id: string | number
  role: "human" | "ai" | "tool" | "system"
  content: string
  thinking?: string
  timestamp?: string
  status?: "pending" | "streaming" | "running" | "completed" | "failed"
  run_id?: string
  node_source?: string
  tool_name?: string
  input?: any
  output?: any
  tool_meta?: {
    display_name?: string
    summary_template?: string
    [key: string]: any
  }
  changeset_count?: number
  changeset_files?: Array<{
    path: string
    operation: 'added' | 'modified' | 'deleted' | 'renamed'
  }>
  attachments?: Array<{
    id: string
    type: string
    url: string
    name: string
    metadata?: any
  }>
  humanRequest?: any
  has_file_operations?: boolean
  references?: any[]
}

interface ChatMessageItemProps {
  msg: Message
  isGrouped?: boolean
  showAvatar?: boolean
  onAddToMemory?: (text: string) => void
  onRewind?: (msg: Message) => void
  onRetry?: (msg: Message) => void
  onQuote?: () => void
  onViewChangeset?: (messageId: string | number, path?: string) => void
}

const ChatMessageItem = memo(
  ({ msg, isGrouped, showAvatar, onAddToMemory, onRewind, onRetry, onQuote, onViewChangeset }: ChatMessageItemProps) => {
    const { t } = useTranslation()
    const { user } = useAuth()
    const { data: config } = useSystemConfig()

    // Hide system prompts from main chat
    if (msg.role === "system") {
      return null
    }

    const userName = user?.nickname || user?.username || t("chat.role.user")
    const deviceName = config?.EVOCLOUD_DEVICE_NAME || t("chat.role.assistant")

    // Render Tool Message (Flat & Compact)
    if (msg.role === "tool") {
      const toolInput = typeof msg.input === 'string' ? msg.input : JSON.stringify(msg.input)
      const truncatedInput = toolInput?.length > 100 ? toolInput.slice(0, 100) + "..." : toolInput

      return (
        <motion.div
          className="group relative flex gap-2 w-full py-1 transition-colors hover:bg-muted/5"
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
        >
          {/* Spine Column */}
          <div className="shrink-0 w-10 flex flex-col items-center relative">
            <div className="absolute top-0 bottom-0 w-[1px] bg-border/40 group-hover:bg-primary/20 transition-colors" />
            <div className="w-2 h-2 rounded-full bg-border mt-3 group-hover:bg-primary/40 transition-colors z-10" />
          </div>

          <div className="flex-1 min-w-0 flex items-center gap-3 py-1 border-b border-border/5">
            <span className="text-[11px] font-bold text-foreground/60 whitespace-nowrap shrink-0">
              {msg.tool_meta?.display_name || msg.tool_name || "TOOL"}
            </span>
            <span className="text-[11px] text-muted-foreground/40 truncate font-mono bg-muted/20 px-1.5 py-0.5 rounded max-w-[400px]">
              {truncatedInput}
            </span>

            {msg.status === "running" && <Loader2 className="h-3 w-3 animate-spin text-primary/40 ml-2" />}
            {msg.changeset_count !== undefined && msg.changeset_count > 0 && (
              <Badge variant="secondary" className="h-4 px-1.5 text-[9px] bg-primary/10 text-primary border-none ml-auto">
                {msg.changeset_count} FILES
              </Badge>
            )}
          </div>
        </motion.div>
      )
    }

    return (
      <motion.div
        className={cn(
          "group relative flex flex-col w-full transition-all",
          isGrouped ? "mt-1" : "mt-4"
        )}
        data-run-id={msg.run_id}
      >
        {/* 1. Header & Avatar */}
        {showAvatar && (
          <div className="flex items-center gap-2 mb-2">
            <div className="shrink-0 w-10 flex flex-col items-center relative">
              {msg.role !== "human" && (
                <div className="absolute top-10 bottom-[-20px] w-[1px] bg-border/40 group-hover:bg-primary/20 transition-colors" />
              )}
              <div className={cn(
                "p-2 rounded-full border transition-colors z-10",
                msg.role === "human" ? "bg-[var(--doc-header-user)] border-primary/20" : "bg-[var(--doc-header-ai)] border-primary/20"
              )}>
                {msg.role === "human" ? <User size={18} className="text-primary" /> : <Bot size={18} className="text-primary" />}
              </div>
            </div>

            <div className={cn(
              "doc-section-header flex-1 flex justify-between items-center rounded-lg px-3 py-1.5 transition-colors border border-border/5",
              msg.role === "human" ? "bg-[var(--doc-header-user)]/40" : "bg-[var(--doc-header-ai)]/40"
            )}>
              <div className="flex items-center gap-3">
                <span className="uppercase tracking-[0.15em] text-[10px] font-bold text-foreground/60">
                  {msg.role === "human" ? userName : deviceName}
                </span>
              </div>

              {/* Right Side: Timestamp or Action Buttons */}
              <div className="relative flex items-center justify-end min-w-[60px]">
                {/* Default: Timestamp */}
                {msg.timestamp && (
                  <div className="text-[10px] text-muted-foreground/30 font-mono opacity-100 group-hover:opacity-0 transition-opacity duration-200 whitespace-nowrap pointer-events-none">
                    {new Date(msg.timestamp).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}
                  </div>
                )}

                {/* Hover: Action Buttons */}
                <div className="absolute right-0 flex items-center gap-0.5 opacity-0 group-hover:opacity-100 transition-opacity duration-200 bg-transparent">
                  {msg.role === "ai" && msg.content && <TTSButton text={msg.content} size="sm" />}
                  
                  {/* Copy */}
                  <Button
                    variant="ghost"
                    size="icon"
                    className="h-7 w-7 rounded-md hover:bg-primary/5 text-muted-foreground/60 hover:text-primary transition-colors"
                    onClick={() => {
                      navigator.clipboard.writeText(msg.content)
                      toast.success(t("chat.interface.copied"))
                    }}
                    title={t("chat.interface.copy")}
                  >
                    <Copy className="h-3.5 w-3.5" />
                  </Button>

                  {/* Quote */}
                  <Button
                    variant="ghost"
                    size="icon"
                    className="h-7 w-7 rounded-md hover:bg-primary/5 text-muted-foreground/60 hover:text-primary transition-colors"
                    onClick={onQuote}
                    title={t("chat.interface.quote")}
                  >
                    <Quote className="h-3.5 w-3.5" />
                  </Button>

                  {/* Memorize */}
                  {onAddToMemory && msg.content && (
                    <Button
                      variant="ghost"
                      size="icon"
                      className="h-7 w-7 rounded-md hover:bg-primary/5 text-muted-foreground/60 hover:text-primary transition-colors"
                      onClick={() => onAddToMemory(msg.content)}
                      title={t("chat.interface.memorize")}
                    >
                      <Brain className="h-3.5 w-3.5" />
                    </Button>
                  )}

                  {/* Rewind (User Only) */}
                  {onRewind && msg.role === "human" && (
                    <Button
                      variant="ghost"
                      size="icon"
                      className="h-7 w-7 rounded-md hover:bg-orange-500/5 text-muted-foreground/60 hover:text-orange-500 transition-colors"
                      onClick={() => onRewind(msg)}
                      title={t("chat.interface.rewind")}
                    >
                      <Undo className="h-3.5 w-3.5" />
                    </Button>
                  )}

                  {/* Retry (User Only) */}
                  {onRetry && msg.role === "human" && (
                    <Button
                      variant="ghost"
                      size="icon"
                      className="h-7 w-7 rounded-md hover:bg-primary/5 text-muted-foreground/60 hover:text-primary transition-colors"
                      onClick={() => onRetry(msg)}
                      title={t("chat.interface.retry")}
                    >
                      <RotateCcw className="h-3.5 w-3.5" />
                    </Button>
                  )}
                </div>
              </div>
            </div>
          </div>
        )}

        {/* 2. Content Section */}
        <div className="flex gap-2">
          {/* Continued Spine */}
          <div className="shrink-0 w-10 flex flex-col items-center relative">
            {msg.role !== "human" && (
              <>
                {!showAvatar && <div className="absolute top-[-20px] bottom-0 w-[1px] bg-border/40 group-hover:bg-primary/20 transition-colors" />}
                {showAvatar && <div className="absolute top-0 bottom-0 w-[1px] bg-border/40" />}
              </>
            )}
          </div>

          <motion.div className="flex-1 min-w-0 transition-all" layout>
            {/* Thinking / Reasoning */}
            {msg.thinking && (
              <Collapsible className="mb-2 overflow-hidden border-l-2 border-primary/10 pl-2">
                <CollapsibleTrigger asChild>
                  <Button variant="ghost" size="sm" className="h-7 px-2 text-[11px] font-semibold text-muted-foreground/60 hover:text-primary transition-colors flex items-center gap-2">
                    <Brain className="h-3 w-3" />
                    {t("chat.interface.thinkingProcess")}
                    <ChevronRight className="h-3 w-3 transition-transform group-data-[state=open]:rotate-90" />
                  </Button>
                </CollapsibleTrigger>
                <CollapsibleContent className="py-2 text-[12.5px] text-muted-foreground/60 italic leading-relaxed">
                  <MessageContent content={typeof msg.thinking === 'string' ? msg.thinking : JSON.stringify(msg.thinking, null, 2)} />
                </CollapsibleContent>
              </Collapsible>
            )}

            {msg.content && (
              <div className="doc-message-content w-full prose-compact transition-opacity">
                <MessageContent content={msg.content} />
              </div>
            )}

            {/* Artifacts / Interactive Elements */}
            {msg.changeset_count !== undefined && msg.changeset_count > 0 && (
              <div className="space-y-4 mt-2">
                <ChangesetSnapshot
                  files={msg.changeset_files || []}
                  totalCount={msg.changeset_count}
                  onViewDetails={(path) => onViewChangeset?.(msg.id, path)}
                />
              </div>
            )}
          </motion.div>
        </div>


      </motion.div>
    )
  },
  (prevProps, nextProps) => {
    return (
      prevProps.msg.id === nextProps.msg.id &&
      prevProps.msg.content === nextProps.msg.content &&
      prevProps.msg.thinking === nextProps.msg.thinking &&
      prevProps.msg.status === nextProps.msg.status &&
      prevProps.showAvatar === nextProps.showAvatar &&
      prevProps.isGrouped === nextProps.isGrouped
    )
  }
)

ChatMessageItem.displayName = "ChatMessageItem"

const globalSpokenMessageIds = new Set<string | number>()
const pageLoadTime = Date.now()

function SmartChatMessageItem(props: ChatMessageItemProps) {
  const { msg } = props
  const { autoSpeak } = useAutoSpeak()
  const { speak, isSpeaking } = useTTS()

  useEffect(() => {
    if (globalSpokenMessageIds.has(msg.id)) return
    const messageTime = msg.timestamp ? new Date(msg.timestamp).getTime() : 0
    if (messageTime > 0 && messageTime < pageLoadTime) {
      globalSpokenMessageIds.add(msg.id)
      return
    }

    if (
      autoSpeak &&
      msg.role === "ai" &&
      msg.content &&
      (!msg.status || msg.status === "completed") &&
      !isSpeaking &&
      (msg.node_source === "chat" || msg.node_source === "finish" || !msg.node_source)
    ) {
      const timer = setTimeout(() => {
        speak(msg.content)
        globalSpokenMessageIds.add(msg.id)
      }, 500)
      return () => clearTimeout(timer)
    }
  }, [autoSpeak, msg.role, msg.content, msg.status, isSpeaking, speak, msg.node_source, msg.id, msg.timestamp])

  return <ChatMessageItem {...props} />
}

export { ChatMessageItem, SmartChatMessageItem }
