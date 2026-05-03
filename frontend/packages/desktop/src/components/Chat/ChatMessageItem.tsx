import {
  Bot,
  Brain,
  ChevronDown,
  ChevronRight,
  Copy,
  MoreHorizontal,
  RotateCcw,
  User,
  Quote,
  Undo,
  Loader2,
} from "lucide-react"
import { ChangesetInlineHint } from "./ChangesetInlineHint"
import { memo } from "react"
import { motion } from "framer-motion"
import { useTranslation } from "react-i18next"
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from "@evoloop/shared/components/ui/collapsible"
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@evoloop/shared/components/ui/dropdown-menu"
import { Avatar, AvatarFallback, AvatarImage } from "@evoloop/shared/components/ui/avatar"
import { Button } from "@evoloop/shared/components/ui/button"
import { TestReportCard } from "./Artifacts/TestReportCard"
import { EChartsArtifact } from "./Artifacts/EChartsArtifact"
import { MapArtifact } from "./Artifacts/MapArtifact"
import { extractArtifactsFromContent } from "./Artifacts/utils"
import { MessageContent } from "./MessageContent"
import { VoiceMessage } from "./VoiceMessage"
import { SourcesFooter } from "./SourcesFooter"

import { AnalysisResultMessage } from "./AnalysisResultMessage"
import { HumanRequestCard } from "./HumanRequestCard"
import { useShowThinking } from "../UserSettings/AppearanceSettings"
import { TTSButton } from "./TTSButton"
import { useAutoSpeak, useTTS } from "@/hooks/useTTS"
import { useEffect } from "react"


export interface Message {
  id: number | string
  role: "human" | "ai" | "tool" | "system"
  content: string
  action_type?: string // Tool output discriminator
  thinking?: string | any[]
  timestamp?: string // ISO timestamp from backend
  run_id?: string // Deep Linking
  parent_id?: string // Parent message ID for threading
  node_source?: "chat" | "finish" | "worker" | "supervisor" | "aggregator" | string // 👈 Agent 节点来源，用于语音播报过滤
  
  // Flattened Tool Fields (from backend MessageBlock)
  tool_name?: string
  tool_call_id?: string
  input?: any
  tool_meta?: {
    display_name?: string
    affected_path_keys?: string[]
    [key: string]: any
  }

  references?: Array<{ // Persistent message references
    id: string
    type: string // memory, file, knowledge, image, audio
    target_id: string // URL or path for images/audio
    target_name: string
    metadata?: { // Additional metadata for audio, etc.
      duration?: number
      waveform?: number[]
      transcript?: string
      [key: string]: any
    }
  }>
  attachments?: Array<{ // For voice messages and other attachments
    id: string
    type: string
    url: string
    name: string
    metadata?: {
      duration?: number
      waveform?: number[]
      transcript?: string
      localPath?: string
      [key: string]: any
    }
  }>
  originalRole?: string // Kept for filtering
  has_file_operations?: boolean // Whether this message has associated file operations (for Rewind/Retry)
  status?: "pending" | "streaming" | "running" | "completed" | "failed" // Message generation status
  // Changeset related (from backend)
  changeset_count: number // Number of files changed in this message (backend provided)
  // HITL request attached to this message
  humanRequest?: {
    id: string
    type: "text" | "choice" | "confirmation" | "approval" | "text_input" | "confirm" | "project_switch"
    prompt: string
    options?: string[]
    context?: string
    payload?: any
    status?: "waiting_human" | "completed" | "cancelled"
  }
  category?: string
  meta_data?: Record<string, any> // Message-level metadata (tool_name, input, tool_meta, etc.)
}

interface ChatMessageItemProps {
  msg: Message
  isGrouped?: boolean
  showAvatar?: boolean
  onAddToMemory?: (text: string) => void
  onRewind?: (msg: Message) => void
  onRetry?: (msg: Message) => void
  onQuote?: () => void
  onViewChangeset?: () => void // Callback when user clicks to view changeset
}

const ChatMessageItem = memo(
  ({ msg, isGrouped, showAvatar, onAddToMemory, onRewind, onRetry, onQuote, onViewChangeset }: ChatMessageItemProps) => {
    const { t } = useTranslation()
    const { showThinking } = useShowThinking()

    // Hide system prompts from main chat
    if (msg.role === "system") {
      return null
    }

    // Render Tool Output as Document Log Block
    if (msg.role === "tool") {
      const displayName = msg.tool_meta?.display_name || msg.meta_data?.tool_name || msg.tool_name || t("chat.messageList.toolExecution")
      const toolInput = msg.input || msg.meta_data?.input
      
      return (
        <div className="flex justify-start mb-6 w-full">
          <div className="w-full max-w-4xl mx-auto pl-12">
            <div className="rounded-lg bg-muted/20 border border-[var(--doc-border)] overflow-hidden shadow-sm">
               <div className="px-3 py-1.5 bg-muted/40 flex items-center gap-2 text-[10px] font-mono uppercase tracking-wider text-muted-foreground/70">
                  <Bot size={12} className="opacity-50" />
                  {displayName}
                  <div className={`ml-auto w-1.5 h-1.5 rounded-full ${msg.status === 'completed' || msg.status === 'done' ? 'bg-primary/40' : 'bg-amber-400 animate-pulse'}`} />
               </div>
               
               {/* Tool Input (Params) - Subtle display */}
               {toolInput && (
                 <div className="px-3 py-2 text-[10px] text-muted-foreground/60 bg-muted/10 border-b border-[var(--doc-border)] italic truncate hover:whitespace-normal hover:break-all transition-all cursor-default">
                    {typeof toolInput === 'string' ? toolInput : JSON.stringify(toolInput)}
                 </div>
               )}

               {msg.content && (
                <div className="p-3 text-xs font-mono text-muted-foreground/80 overflow-x-auto whitespace-pre-wrap leading-relaxed">
                    {msg.content}
                </div>
               )}
            </div>
          </div>
        </div>
      )
    }

    return (
      <motion.div
        initial={{ opacity: 0, y: 10 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.3 }}
        data-run-id={msg.run_id}
        className="group relative flex flex-col w-full mb-4"
      >
        {/* Document Spine Line */}
        <div className="chat-timeline-spine" />

        {/* 1. Header Section */}
        <div className="flex items-center gap-2 relative z-10 w-full mb-1">
          <div className="shrink-0 w-10 flex flex-col items-center">
            <div className={`p-2 rounded-full border transition-colors ${
              msg.role === "human" 
                ? "bg-[var(--doc-header-user)] border-primary/20" 
                : "bg-[var(--doc-header-ai)] border-primary/20"
            }`}>
              {msg.role === "human" ? (
                <User size={18} className="text-primary" />
              ) : (
                <Bot size={18} className="text-primary" />
              )}
            </div>
          </div>

          <div className={`doc-section-header flex-1 flex justify-between items-center transition-colors ${
            msg.role === "human" ? "bg-[var(--doc-header-user)]/80" : "bg-[var(--doc-header-ai)]/80"
          }`}>
            <div className="flex items-center gap-3">
              <span className="uppercase tracking-[0.15em] text-[10px] font-bold text-foreground/60">
                {msg.role === "human" ? t("chat.role.user") : t("chat.role.assistant")}
              </span>
              {msg.run_id && (
                <span className="text-[9px] font-mono opacity-20 px-1.5 py-0.5 rounded border border-foreground/10">
                  {msg.run_id}
                </span>
              )}
            </div>

            {/* Header Actions - Minimalist */}
            <div className="flex items-center gap-1 opacity-0 group-hover:opacity-100 transition-all">
               <Button
                variant="ghost"
                size="icon"
                className="h-7 w-7 rounded-md hover:bg-primary/5 text-muted-foreground/60 hover:text-primary transition-colors"
                onClick={() => navigator.clipboard.writeText(msg.content)}
                title={t("chat.interface.copy")}
              >
                <Copy className="h-3.5 w-3.5" />
              </Button>

              {msg.role === "human" && onRetry && (
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

              {msg.role === "human" && onRewind && (
                 <Button
                  variant="ghost"
                  size="icon"
                  className="h-7 w-7 rounded-md hover:bg-primary/5 text-muted-foreground/60 hover:text-primary transition-colors"
                  onClick={() => onRewind(msg)}
                  title={t("chat.interface.rewind")}
                >
                  <Undo className="h-3.5 w-3.5" />
                </Button>
              )}
              {msg.role === "ai" && msg.content && <TTSButton text={msg.content} size="xs" />}
              
              <DropdownMenu>
                <DropdownMenuTrigger asChild>
                  <Button variant="ghost" size="icon" className="h-7 w-7 rounded-md text-muted-foreground/60">
                    <MoreHorizontal className="h-3.5 w-3.5" />
                  </Button>
                </DropdownMenuTrigger>
                <DropdownMenuContent align="end" className="w-40">
                   {msg.role === "ai" && onAddToMemory && (
                    <DropdownMenuItem onClick={() => onAddToMemory(msg.content)}>
                      <Brain className="mr-2 h-4 w-4 opacity-70" /> {t("chat.interface.memorize")}
                    </DropdownMenuItem>
                  )}
                   {onRetry && msg.role === "human" && (
                    <DropdownMenuItem onClick={() => onRetry(msg)}>
                      <RotateCcw className="mr-2 h-4 w-4 opacity-70" /> {t("chat.interface.retry")}
                    </DropdownMenuItem>
                  )}
                  {onRewind && msg.role === "human" && (
                    <DropdownMenuItem onClick={() => onRewind(msg)}>
                      <Undo className="mr-2 h-4 w-4 opacity-70" /> {t("chat.interface.rewind")}
                    </DropdownMenuItem>
                  )}
                  {onQuote && (
                    <DropdownMenuItem onClick={() => onQuote()}>
                      <Quote className="mr-2 h-4 w-4 opacity-70" /> {t("chat.interface.quote")}
                    </DropdownMenuItem>
                  )}
                </DropdownMenuContent>
              </DropdownMenu>
            </div>
          </div>
        </div>

        {/* 2. Content Section */}
        <div className="doc-message-content relative z-10 w-full min-w-0">
          
          {/* Action Stream (Thinking + Steps) - AI ONLY */}
          {msg.role === "ai" && (
            <div className="chat-action-stream empty:hidden animate-in fade-in slide-in-from-top-2 duration-700">
              {/* Reasoning/Thinking Block */}
              {showThinking && (() => {
                const thinkingContent = msg.thinking ?? ""
                if (!thinkingContent) return null
                if (msg.status === "streaming" && !msg.content) return null

                return (
                  <Collapsible defaultOpen={false} className="w-full mb-3 last:mb-0">
                    <CollapsibleTrigger asChild>
                      <Button
                        variant="ghost"
                        size="sm"
                        className="h-6 px-0 text-[10px] text-muted-foreground/60 hover:bg-transparent flex items-center gap-2 w-full justify-start font-mono group/trigger"
                      >
                        <ChevronRight className="h-3 w-3 group-data-[state=open]/trigger:rotate-90 transition-transform opacity-40" />
                        <span className="uppercase tracking-wider opacity-60 font-bold">
                          {t("chat.interface.thinkingProcess")}
                        </span>
                      </Button>
                    </CollapsibleTrigger>
                    <CollapsibleContent className="text-[11px] leading-relaxed text-muted-foreground/70 pl-5 border-l border-primary/10 break-all mt-2 mb-2">
                      <MessageContent content={thinkingContent} />
                    </CollapsibleContent>
                  </Collapsible>
                )
              })()}

               {/* Tool Execution Steps are now shown as independent messages or in the side panel */}
            </div>
          )}

          {/* Main Body */}
          <div className="w-full min-w-0">
            {(msg.content || msg.status === "streaming") ? (
              <>
                {(() => {
                  let processedContent = msg.content
                  if (msg.role === "ai" && msg.status !== "streaming") {
                    const parts = extractArtifactsFromContent(processedContent)
                    if (parts.length > 0) {
                      return (
                        <div className="flex flex-col gap-6">
                          {parts.map((part, idx) => {
                            if (part.type === 'text') {
                              return <MessageContent key={idx} content={part.content!} isUser={msg.role === "human"} />
                            }
                            if (part.artifactType === "test_report") return <TestReportCard key={idx} data={part.data} />
                            if (part.artifactType === "echarts") return <EChartsArtifact key={idx} data={part.data} />
                            if (part.artifactType === "map") return <MapArtifact key={idx} data={part.data} />
                            if (part.artifactType === "requirement_analysis") {
                                return (
                                  <AnalysisResultMessage
                                    key={idx}
                                    analysisId={part.data.analysis_id}
                                    documentId={part.data.document_id}
                                    projectId={part.data.project_id}
                                    data={part.data.analysis}
                                  />
                                )
                            }
                            return null
                          })}
                        </div>
                      )
                    }
                  }

                  // Voice message
                  const voiceAttachment = msg.attachments?.find(att => att.type === 'audio')
                  if (voiceAttachment) {
                    return (
                      <VoiceMessage
                        audioUrl={voiceAttachment.url}
                        duration={voiceAttachment.metadata?.duration || 0}
                        waveform={voiceAttachment.metadata?.waveform}
                        transcript={voiceAttachment.metadata?.transcript || (msg.content !== '[语音消息]' ? msg.content : undefined)}
                        isUser={msg.role === "human"}
                      />
                    )
                  }

                  return <MessageContent content={processedContent} isUser={msg.role === "human"} />
                })()}
                {msg.status === "streaming" && (
                  <span className="inline-block w-1 h-4 ml-1 align-middle bg-primary/60 animate-pulse rounded-full" />
                )}
              </>
            ) : (
              <div className="flex items-center gap-3 text-xs text-muted-foreground/40 italic py-4 pl-2">
                <Loader2 className="h-3.5 w-3.5 animate-spin opacity-50" />
                {t("chat.interface.agentThinking")}
              </div>
            )}
          </div>

          {/* Post-content blocks */}
          <div className="mt-2 flex flex-col gap-4">
            {msg.role === "ai" && msg.humanRequest && (
              <HumanRequestCard 
                request={{
                  ...msg.humanRequest,
                  status: msg.humanRequest.status || (msg.status as any) // Fallback to message status
                }} 
              />
            )}
            
            {msg.role === "ai" && msg.references && msg.references.length > 0 && (
              <SourcesFooter
                references={msg.references.map(ref => ({
                  type: ref.type,
                  name: ref.target_name,
                  path: ref.target_id
                }))}
              />
            )}

            {msg.role === "ai" && !!msg.changeset_count && msg.changeset_count > 0 && (
              <div className="pt-4 border-t border-[var(--doc-border)]">
                <ChangesetInlineHint
                  fileCount={msg.changeset_count}
                  messageId={msg.id}
                  onClick={onViewChangeset}
                />
              </div>
            )}
          </div>
        </div>

        {/* Timestamp - Minimalist floating */}
        {msg.timestamp && (
          <div className="absolute top-2 right-4 text-[9px] text-muted-foreground/20 font-mono opacity-0 group-hover:opacity-100 transition-opacity pointer-events-none">
            {new Date(msg.timestamp).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}
          </div>
        )}
      </motion.div>
    )
  },
  (prevProps, nextProps) => {
    // Custom Comparison for Performance
    // We only re-render if:
    // 1. Message ID changed (different message)
    // 2. Content string changed
    // 3. Thinking string changed
    // We IGNORE handler function references changes (they are stable in effect, or we simply don't care about their closure since they access stable Mutation objects usually)
    // Actually, mutations in ChatInterface are created via useMutation hook which returns a stable `mutate` function?
    // useMutation returns an object { mutate, ... }. The `mutate` function reference might change if options change.
    // However, usually it's fine.
    // Crucially: we compare content.
    return (
      prevProps.msg.id === nextProps.msg.id &&
      prevProps.msg.content === nextProps.msg.content &&
      prevProps.msg.thinking === nextProps.msg.thinking &&
      prevProps.msg.meta_data === nextProps.msg.meta_data &&
      prevProps.msg.status === nextProps.msg.status
    )
  },
)

ChatMessageItem.displayName = "ChatMessageItem"

// 👇 全局 Set，用于记录已播报的消息 ID（跨组件、跨会话）
const globalSpokenMessageIds = new Set<string | number>()

// 👇 记录页面加载时间，只播报加载后收到的消息
const pageLoadTime = Date.now()

// Wrapper component with auto-speak functionality
function SmartChatMessageItem(props: ChatMessageItemProps) {
  const { msg } = props
  const { autoSpeak } = useAutoSpeak()
  const { speak, isSpeaking } = useTTS()

  // Auto-speak AI messages when they complete
  // 👇 只播报 chat 和 finish 节点的消息，过滤掉 worker/supervisor 的技术性内容
  useEffect(() => {
    // 👇 检查是否已经播报过这条消息（全局去重）
    if (globalSpokenMessageIds.has(msg.id)) {
      return
    }

    // 👇 检查消息是否在页面加载前就已存在（历史消息不播报）
    // 如果消息没有 timestamp 或者 timestamp 早于页面加载时间，认为是历史消息
    const messageTime = msg.timestamp ? new Date(msg.timestamp).getTime() : 0
    if (messageTime > 0 && messageTime < pageLoadTime) {
      // 标记为已播报（跳过）
      globalSpokenMessageIds.add(msg.id)
      return
    }

    if (
      autoSpeak &&
      msg.role === "ai" &&
      msg.content &&
      (!msg.status || msg.status === "completed") &&
      !isSpeaking &&
      // 只播报 chat 和 finish 节点的消息
      (msg.node_source === "chat" || msg.node_source === "finish" || !msg.node_source)
    ) {
      // Small delay to not interrupt the user
      const timer = setTimeout(() => {
        speak(msg.content)
        // 标记为已播报
        globalSpokenMessageIds.add(msg.id)
      }, 500)

      return () => clearTimeout(timer)
    }
  }, [autoSpeak, msg.role, msg.content, msg.status, isSpeaking, speak, msg.node_source, msg.id, msg.timestamp])

  return <ChatMessageItem {...props} />
}

export { ChatMessageItem, SmartChatMessageItem }
