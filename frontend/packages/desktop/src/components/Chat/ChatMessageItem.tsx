import { Badge } from "@evoloop/shared/components/ui/badge"
import { Button } from "@evoloop/shared/components/ui/button"
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from "@evoloop/shared/components/ui/collapsible"
import { motion } from "framer-motion"
import {
  Brain,
  ChevronRight,
  Copy,
  Loader2,
  Quote,
  RotateCcw,
  Undo,
} from "lucide-react"
import { memo, useEffect } from "react"
import { useTranslation } from "react-i18next"
import { toast } from "sonner"
import { useAutoSpeak, useTTS } from "@/hooks/useTTS"
import { previewFile } from "@/utils/fileLinkHandler"
import { resolveReferencePreview } from "@/utils/fileUtils"
import { ChangesetSnapshot } from "./ChangesetSnapshotView"
import { MessageContent } from "./MessageContent"
import { MessageReferences } from "./MessageReferences"
import { TTSButton } from "./TTSButton"

export interface MessageReference {
  id: string
  type:
    | "file"
    | "image"
    | "audio"
    | "message"
    | "artifact"
    | "changeset"
    | "skill"
  target_id: string
  target_name: string
  meta_data?: Record<string, any>
}

export interface Message {
  id: string | number
  role: "human" | "ai" | "tool" | "system"
  content: string
  thinking?: string
  timestamp?: string
  status?:
    | "pending"
    | "streaming"
    | "running"
    | "completed"
    | "failed"
    | "waiting_human"
  run_id?: string
  tool_name?: string
  input?: any
  output?: any
  tool_meta?: {
    display_name?: string
    summary_template?: string
    [key: string]: any
  }
  changeset_count?: number
  isLastInTurn?: boolean

  changeset_files?: Array<{
    path: string
    operation: "added" | "modified" | "deleted" | "renamed"
  }>
  humanRequest?: any
  has_file_operations?: boolean
  references?: MessageReference[]
  effective_content?: string
  turnDuration?: string
}

const formatSmartTimestamp = (timestamp?: string) => {
  if (!timestamp) return ""
  const date = new Date(timestamp)
  if (Number.isNaN(date.getTime())) return ""

  const now = new Date()
  const isToday =
    date.getDate() === now.getDate() &&
    date.getMonth() === now.getMonth() &&
    date.getFullYear() === now.getFullYear()

  const timeStr = date.toLocaleTimeString([], {
    hour: "2-digit",
    minute: "2-digit",
  })

  if (isToday) {
    return timeStr
  }
  const dateStr = date.toLocaleDateString([], {
    month: "short",
    day: "numeric",
  })
  return `${dateStr} ${timeStr}`
}

interface ChatMessageItemProps {
  msg: Message
  isGrouped?: boolean
  showAvatar?: boolean
  onAddToMemory?: (text: string) => void
  onRewind?: (msg: Message) => void
  onRetry?: (msg: Message) => void
  onQuote?: () => void
  onViewChangeset?: (
    messageId: string | number,
    path?: string,
    diff?: string,
  ) => void
  isActivelyStreaming?: boolean
}

const chatMessagePropsAreEqual = (
  prevProps: ChatMessageItemProps,
  nextProps: ChatMessageItemProps,
) => {
  return (
    prevProps.msg.id === nextProps.msg.id &&
    prevProps.msg.content === nextProps.msg.content &&
    prevProps.msg.effective_content === nextProps.msg.effective_content &&
    prevProps.msg.turnDuration === nextProps.msg.turnDuration &&
    prevProps.msg.isLastInTurn === nextProps.msg.isLastInTurn &&
    prevProps.msg.thinking === nextProps.msg.thinking &&
    prevProps.msg.status === nextProps.msg.status &&
    prevProps.showAvatar === nextProps.showAvatar &&
    prevProps.isGrouped === nextProps.isGrouped &&
    prevProps.isActivelyStreaming === nextProps.isActivelyStreaming
  )
}

const ChatMessageItem = memo(
  ({
    msg,
    isActivelyStreaming,
    onAddToMemory,
    onRewind,
    onRetry,
    onQuote,
    onViewChangeset,
    isGrouped,
    showAvatar,
  }: ChatMessageItemProps) => {
    const { t } = useTranslation()

    // Hide system prompts from main chat
    if (msg.role === "system") {
      return null
    }

    const isUser = msg.role === "human"
    const actionContent =
      msg.effective_content !== undefined && msg.effective_content.trim() !== ""
        ? msg.effective_content
        : msg.content

    // Render Tool Message (Flat & Compact)
    if (msg.role === "tool") {
      return (
        <motion.div
          className="group relative flex items-center gap-2.5 w-full py-1 px-3 my-0.5 rounded transition-colors font-mono text-[12px] text-muted-foreground/70 hover:text-muted-foreground bg-muted/10 hover:bg-muted/25"
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          transition={{ duration: 0.1 }}
        >
          <div className="w-1.5 h-1.5 rounded-full bg-primary/50 shrink-0" />
          <span
            className="truncate flex-1"
            title={msg.tool_meta?.display_name || msg.tool_name || "TOOL"}
          >
            {msg.tool_meta?.display_name || msg.tool_name || "TOOL"}
          </span>
          {msg.status === "running" && (
            <Loader2 className="h-3 w-3 animate-spin text-primary ml-2 shrink-0" />
          )}
          {msg.changeset_count !== undefined && msg.changeset_count > 0 && (
            <Badge
              variant="secondary"
              className="h-4 px-1.5 text-[9px] bg-primary/10 text-primary border-none shrink-0 ml-auto"
            >
              {msg.changeset_count}{" "}
              {t("chat.interface.files", { defaultValue: "FILES" })}
            </Badge>
          )}
        </motion.div>
      )
    }

    // 1. User Message Layout (Ultra compact: no bottom line, no timestamp, actions folded in absolute hover pill)
    if (isUser) {
      return (
        <motion.div
          className="group relative flex flex-col w-full my-2.5 px-4 py-3.5 rounded-xl bg-primary text-primary-foreground text-[15px] font-medium leading-relaxed transition-all shadow-sm"
          data-run-id={msg.run_id}
        >
          <MessageContent content={msg.content} isUser={isUser} />
          <MessageReferences references={msg.references || []} isUser={true} />

          {/* Absolute Hover Action Pill (Folded into top-right corner on hover, saving vertical space) */}
          <div className="absolute top-1.5 right-1.5 flex items-center gap-0.5 opacity-0 group-hover:opacity-100 transition-opacity duration-150 bg-background/90 backdrop-blur-sm px-1 py-0.5 rounded-md shadow-sm border border-border/40 z-10">
            {/* Copy */}
            <Button
              variant="ghost"
              size="icon"
              className="h-6 w-6 rounded hover:bg-muted text-muted-foreground/80 hover:text-foreground"
              onClick={() => {
                navigator.clipboard.writeText(actionContent || "")
                toast.success(t("chat.interface.copied"))
              }}
              title={t("chat.interface.copy")}
            >
              <Copy className="h-3 w-3" />
            </Button>
            {/* Quote */}
            <Button
              variant="ghost"
              size="icon"
              className="h-6 w-6 rounded hover:bg-muted text-muted-foreground/80 hover:text-foreground"
              onClick={onQuote}
              title={t("chat.interface.quote")}
            >
              <Quote className="h-3 w-3" />
            </Button>
            {/* Memorize */}
            {onAddToMemory && actionContent && (
              <Button
                variant="ghost"
                size="icon"
                className="h-6 w-6 rounded hover:bg-muted text-muted-foreground/80 hover:text-foreground"
                onClick={() => onAddToMemory(actionContent)}
                title={t("chat.interface.memorize")}
              >
                <Brain className="h-3 w-3" />
              </Button>
            )}
            {/* Rewind */}
            {onRewind && (
              <Button
                variant="ghost"
                size="icon"
                className="h-6 w-6 rounded hover:bg-orange-500/10 text-muted-foreground/80 hover:text-orange-500"
                onClick={() => onRewind(msg)}
                title={t("chat.interface.rewind")}
              >
                <Undo className="h-3 w-3" />
              </Button>
            )}
            {/* Retry */}
            {onRetry && (
              <Button
                variant="ghost"
                size="icon"
                className="h-6 w-6 rounded hover:bg-primary/10 text-muted-foreground/80 hover:text-primary"
                onClick={() => onRetry(msg)}
                title={t("chat.interface.retry")}
              >
                <RotateCcw className="h-3 w-3" />
              </Button>
            )}
          </div>
        </motion.div>
      )
    }

    // 2. AI Message Layout (Compact transparent document flow with bottom action bar)
    const isCurrentlyStreaming =
      isActivelyStreaming ?? msg.status === "streaming"
    return (
      <motion.div
        className="group relative flex flex-col mx-4 my-1 text-foreground text-[14px] transition-all"
        data-run-id={msg.run_id}
      >
        {/* Thinking section (tight margin) */}
        {msg.thinking && (
          <Collapsible className="mb-2 overflow-hidden">
            <CollapsibleTrigger
              asChild
              disabled={!msg.content && isCurrentlyStreaming}
            >
              <Button
                variant="ghost"
                size="sm"
                className="group/trigger h-6 px-2 rounded text-[11px] font-medium text-muted-foreground hover:text-foreground transition-colors hover:bg-muted/40 flex items-center gap-1.5"
              >
                <Brain className="h-3 w-3 text-primary/70" />
                <span>
                  {!msg.content && isCurrentlyStreaming
                    ? t("chat.interface.thinking", {
                        defaultValue: "Thinking...",
                      })
                    : t("chat.interface.thinkingProcess", {
                        defaultValue: "Worked for thought",
                      })}
                </span>
                {!msg.content && isCurrentlyStreaming ? (
                  <Loader2 className="h-3 w-3 animate-spin text-muted-foreground/50" />
                ) : (
                  <ChevronRight className="h-3 w-3 transition-transform group-data-[state=open]/trigger:rotate-90 text-muted-foreground/50" />
                )}
              </Button>
            </CollapsibleTrigger>
            {(msg.content || !isCurrentlyStreaming) && (
              <CollapsibleContent className="mt-1 pl-3 py-1 border-l-1 border-border/60 text-[12px] text-muted-foreground/80 leading-relaxed font-mono">
                <MessageContent
                  content={
                    typeof msg.thinking === "string"
                      ? msg.thinking
                      : JSON.stringify(msg.thinking, null, 2)
                  }
                />
              </CollapsibleContent>
            )}
          </Collapsible>
        )}

        {/* AI Main Content */}
        {msg.content && (
          <div className="doc-message-content w-full prose-compact transition-opacity leading-relaxed">
            <MessageContent content={msg.content} />
            <MessageReferences
              references={(msg.references || []).filter(
                (r) => r.type !== "artifact",
              )}
              onReferenceClick={(ref) => {
                if (ref.type === "changeset") {
                  onViewChangeset?.(msg.id)
                  return
                }

                const preview = resolveReferencePreview(ref)
                if (preview) {
                  previewFile(preview.path, preview.name)
                }
              }}
            />
          </div>
        )}

        {/* Artifacts view */}
        {msg.changeset_count !== undefined && msg.changeset_count > 0 && (
          <div className="mt-2 my-1">
            <ChangesetSnapshot
              files={msg.changeset_files || []}
              totalCount={msg.changeset_count}
              onViewDetails={(path, diff) =>
                onViewChangeset?.(msg.id, path, diff)
              }
            />
          </div>
        )}

        {/* Footer Action & Timestamp (Only show timestamp and action buttons for the last AI message in turn) */}
        {msg.isLastInTurn && (
          <div className="flex items-center justify-between mt-2 pt-1.5 border-t border-border/15 text-[11px] text-muted-foreground/40 font-mono">
            <span className="flex items-center gap-1.5 font-mono">
              <span>{formatSmartTimestamp(msg.timestamp)}</span>
              {msg.turnDuration && (
                <span className="opacity-60 text-[10px]">
                  ({msg.turnDuration})
                </span>
              )}
            </span>

            <div className="flex items-center gap-0.5 text-muted-foreground/60">
              {actionContent && (
                <TTSButton
                  text={actionContent}
                  size="sm"
                  className="h-6 w-6 rounded hover:bg-muted/60 hover:text-foreground text-muted-foreground/70 transition-colors"
                />
              )}

              <Button
                variant="ghost"
                size="icon"
                className="h-6 w-6 rounded hover:bg-muted/60 hover:text-foreground text-muted-foreground/70 transition-colors"
                onClick={() => {
                  navigator.clipboard.writeText(actionContent || "")
                  toast.success(t("chat.interface.copied"))
                }}
                title={t("chat.interface.copy")}
              >
                <Copy className="h-3 w-3" />
              </Button>

              <Button
                variant="ghost"
                size="icon"
                className="h-6 w-6 rounded hover:bg-muted/60 hover:text-foreground text-muted-foreground/70 transition-colors"
                onClick={onQuote}
                title={t("chat.interface.quote")}
              >
                <Quote className="h-3 w-3" />
              </Button>

              {onAddToMemory && actionContent && (
                <Button
                  variant="ghost"
                  size="icon"
                  className="h-6 w-6 rounded hover:bg-muted/60 hover:text-foreground text-muted-foreground/70 transition-colors"
                  onClick={() => onAddToMemory(actionContent)}
                  title={t("chat.interface.memorize")}
                >
                  <Brain className="h-3 w-3" />
                </Button>
              )}
            </div>
          </div>
        )}
      </motion.div>
    )
  },
  chatMessagePropsAreEqual,
)

ChatMessageItem.displayName = "ChatMessageItem"

const globalSpokenMessageIds = new Set<string | number>()
const pageLoadTime = Date.now()

const SmartChatMessageItem = memo((props: ChatMessageItemProps) => {
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

    const speakContent =
      msg.effective_content !== undefined && msg.effective_content.trim() !== ""
        ? msg.effective_content
        : msg.content

    if (
      autoSpeak &&
      msg.role === "ai" &&
      speakContent &&
      (!msg.status || msg.status === "completed") &&
      !isSpeaking
    ) {
      const timer = setTimeout(() => {
        speak(speakContent)
        globalSpokenMessageIds.add(msg.id)
      }, 500)
      return () => clearTimeout(timer)
    }
  }, [
    autoSpeak,
    msg.role,
    msg.content,
    msg.effective_content,
    msg.status,
    isSpeaking,
    speak,
    msg.id,
    msg.timestamp,
  ])

  return <ChatMessageItem {...props} />
}, chatMessagePropsAreEqual)

export { ChatMessageItem, SmartChatMessageItem }
