import { ThinkingBlock, ToolCallItem } from "@evoloop/shared"
import { Button } from "@evoloop/shared/components/ui/button"
import { motion } from "framer-motion"
import { Brain, Copy, Quote, RotateCcw, Undo } from "lucide-react"
import { memo, useEffect, useState } from "react"
import { useTranslation } from "react-i18next"
import { toast } from "sonner"
import { useAutoSpeak, useTTS } from "@/hooks/useTTS"
import { previewFile } from "@/utils/fileLinkHandler"
import { resolveReferencePreview } from "@/utils/fileUtils"
import { ChangesetSnapshot } from "./ChangesetSnapshotView"
import { type GalleryImage, ImageGalleryViewer } from "./ImageGalleryViewer"
import { MessageContent } from "./MessageContent"
import { MessageReferences } from "./MessageReferences"
import { TaskProposalCard } from "./TaskProposalCard"
import { TTSButton } from "./TTSButton"

export interface MessageReference {
  id: string
  type:
    | "file"
    | "directory"
    | "image"
    | "video"
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
  sequence_number?: number
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
  is_remembered?: boolean
  memory_concept_id?: string | null

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
  onAddToMemory?: (
    text: string,
    messageId: string | number,
    isRemembered?: boolean,
  ) => void
  onRewind?: (msg: Message) => void
  onRetry?: (msg: Message) => void
  onQuote?: () => void
  onViewChangeset?: (
    messageId: string | number,
    path?: string,
    diff?: string,
  ) => void
  /** 打开会话级图片 Gallery（跨消息收集全部图片）；未提供时回退到本条消息内浏览 */
  onOpenImageGallery?: (ref: MessageReference) => void
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
    prevProps.msg.is_remembered === nextProps.msg.is_remembered &&
    prevProps.msg.memory_concept_id === nextProps.msg.memory_concept_id &&
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
    onOpenImageGallery,
  }: ChatMessageItemProps) => {
    const { t } = useTranslation()

    // Hide system prompts from main chat.
    // ErrorEmitter 单出口契约：仅系统级错误块（category==="error"）可见，
    // 其余 system 消息不渲染。
    if (msg.role === "system") {
      if ((msg as { category?: string }).category !== "error") {
        return null
      }
    }

    // Hide HITL tool messages
    if (
      msg.role === "tool" &&
      (msg.tool_name === "ask_human" || msg.tool_name === "ask_confirm")
    ) {
      return null
    }

    const isUser = msg.role === "human"
    // 值守系统代用户发起的消息（任务评审回灌/转人工仲裁）：识别前缀，
    // 剥掉前缀渲染并打上"值守系统代发"徽标，与用户亲口说的话区分
    const SYSTEM_ON_BEHALF_PREFIX = "[值守系统代用户]"
    const rawContent =
      msg.effective_content !== undefined && msg.effective_content.trim() !== ""
        ? msg.effective_content
        : msg.content
    const isSystemOnBehalf =
      isUser && (rawContent || "").trim().startsWith(SYSTEM_ON_BEHALF_PREFIX)
    const [gallery, setGallery] = useState<{
      images: GalleryImage[]
      index: number
    } | null>(null)
    const galleryUI = (
      <ImageGalleryViewer
        images={gallery?.images || []}
        index={gallery?.index || 0}
        open={!!gallery}
        onIndexChange={(index) => setGallery((g) => (g ? { ...g, index } : g))}
        onClose={() => setGallery(null)}
      />
    )
    const actionContent =
      msg.effective_content !== undefined && msg.effective_content.trim() !== ""
        ? msg.effective_content
        : msg.content
    const onBehalfRender =
      isSystemOnBehalf &&
      (actionContent || "").trim().startsWith(SYSTEM_ON_BEHALF_PREFIX)
        ? (actionContent || "")
            .trim()
            .slice(SYSTEM_ON_BEHALF_PREFIX.length)
            .trim()
        : actionContent

    // Render Tool Message (Flat & Compact)
    if (msg.role === "tool") {
      const proposalInput =
        msg.input && typeof msg.input === "object"
          ? (msg.input as Record<string, unknown>)
          : {}
      if (
        msg.tool_name === "tasks" &&
        proposalInput.action === "create" &&
        proposalInput.source === "agent"
      ) {
        return (
          <TaskProposalCard
            msg={{ id: msg.id, content: msg.content, input: proposalInput }}
          />
        )
      }

      // 后端 display_name 是单行摘要模板，长值（命令/正则/SQL/提示词等）会被
      // 内嵌并压成一行 —— 检测摘要中内嵌的长值/多行值，剥离为多行块渲染。
      // 匹配必须用未经空白清理的原始串（heredoc/缩进命令含连续空白，
      // 预清理会破坏 includes 匹配），清理放到剥离之后。
      // 仅当值确实内嵌在摘要中时才剥离（write/edit 的 content 不在摘要内，
      // 归 changeset 呈现，不在此渲染）；question（image/video analyze）不在
      // 摘要内，长问题时仅以块补充。
      const rawDisplayName = (
        msg.tool_meta?.display_name ||
        msg.tool_name ||
        t("chat.toolMessage.fallbackName")
      ).trim()
      const toolInput = proposalInput
      const rawAction =
        typeof toolInput.action === "string" ? toolInput.action : ""

      const actionLabel =
        rawAction && msg.tool_name
          ? t(`chat.toolAction.${msg.tool_name}.${rawAction}`, {
              defaultValue: "",
            })
          : ""
      const toolLabel = msg.tool_name
        ? t(`chat.toolName.${msg.tool_name}`, { defaultValue: "" })
        : ""
      const semanticLabel = actionLabel || toolLabel

      return (
        <ToolCallItem
          data={{
            toolName: msg.tool_name || "",
            displayName: semanticLabel || rawDisplayName,
            input: toolInput,
            output: msg.output,
            status: msg.status,
            changesetCount: msg.changeset_count,
          }}
          variant="compact"
        />
      )
    }

    const handleReferenceClick = (ref: MessageReference) => {
      if (ref.type === "changeset") {
        onViewChangeset?.(msg.id)
        return
      }

      // 图片引用 → Gallery 查看器（优先会话级：跨消息浏览全部图片）
      if (ref.type === "image") {
        if (onOpenImageGallery) {
          onOpenImageGallery(ref)
          return
        }
        const images = (msg.references || [])
          .filter((r) => r.type === "image" && r.target_id)
          .map((r) => ({
            url: r.target_id,
            name: r.target_name || r.target_id,
          }))
        if (images.length > 0) {
          const idx = images.findIndex((im) => im.url === ref.target_id)
          setGallery({ images, index: Math.max(idx, 0) })
          return
        }
      }

      const preview = resolveReferencePreview(ref)
      if (preview) {
        // Dispatch locate event for file tree auto-expansion
        window.dispatchEvent(
          new CustomEvent("locate-file", {
            detail: { path: preview.path },
          }),
        )
        // Preview if it's a file
        if (ref.type !== "directory") {
          previewFile(preview.path, preview.name)
        }
      }
    }

    // 1. User Message Layout (Ultra compact: no bottom line, no timestamp, actions folded in absolute hover pill)
    if (isUser) {
      return (
        <>
          <motion.div
            className={`chat-bubble-user group relative flex flex-col w-full my-2.5 px-4 py-3.5 rounded-xl text-[15px] font-medium leading-relaxed transition-all ${
              isSystemOnBehalf
                ? "border border-violet-400/40 bg-violet-500/[0.06]"
                : ""
            }`}
            data-run-id={msg.run_id}
          >
            {isSystemOnBehalf && (
              <span className="inline-flex items-center gap-1 self-start shrink-0 mb-1 rounded-full bg-violet-500/10 text-violet-600 dark:text-violet-400 text-[9px] font-bold px-1.5 py-0.5">
                值守系统代发·任务结果
              </span>
            )}
            <MessageContent
              content={isSystemOnBehalf ? onBehalfRender : msg.content}
              isUser={isUser}
            />
            <MessageReferences
              references={msg.references || []}
              isUser={true}
              content={msg.content}
              onReferenceClick={handleReferenceClick}
            />

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
                  className={`h-6 w-6 rounded hover:bg-muted ${
                    msg.is_remembered
                      ? "text-primary fill-primary"
                      : "text-muted-foreground/80 hover:text-foreground"
                  }`}
                  onClick={() =>
                    onAddToMemory(actionContent, msg.id, msg.is_remembered)
                  }
                  title={
                    msg.is_remembered
                      ? t("chat.interface.forget")
                      : t("chat.interface.memorize")
                  }
                >
                  <Brain
                    className={`h-3 w-3 ${msg.is_remembered ? "fill-current" : ""}`}
                  />
                </Button>
              )}
              {/* Rewind */}
              {onRewind && (
                <Button
                  variant="ghost"
                  size="icon"
                  className="h-6 w-6 rounded hover:bg-warning/10 text-muted-foreground/80 hover:text-warning"
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
          {galleryUI}
        </>
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
        {/* Thinking section */}
        {msg.thinking && (
          <ThinkingBlock
            data={{
              thinking:
                typeof msg.thinking === "string"
                  ? msg.thinking
                  : JSON.stringify(msg.thinking, null, 2),
              isStreaming: !msg.content && isCurrentlyStreaming,
              duration: msg.turnDuration,
            }}
            renderContent={(content) => <MessageContent content={content} />}
          />
        )}

        {/* AI Main Content */}
        {msg.content && (
          <div className="doc-message-content w-full prose-compact transition-opacity leading-relaxed">
            <MessageContent content={msg.content} />
            <MessageReferences
              references={(msg.references || []).filter(
                (r) => r.type !== "artifact",
              )}
              content={msg.content}
              onReferenceClick={handleReferenceClick}
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
                  className={`h-6 w-6 rounded hover:bg-muted/60 ${
                    msg.is_remembered
                      ? "text-primary fill-primary"
                      : "text-muted-foreground/70 hover:text-foreground"
                  }`}
                  onClick={() =>
                    onAddToMemory(actionContent, msg.id, msg.is_remembered)
                  }
                  title={
                    msg.is_remembered
                      ? t("chat.interface.forget")
                      : t("chat.interface.memorize")
                  }
                >
                  <Brain
                    className={`h-3 w-3 ${msg.is_remembered ? "fill-current" : ""}`}
                  />
                </Button>
              )}
            </div>
          </div>
        )}
        {galleryUI}
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
