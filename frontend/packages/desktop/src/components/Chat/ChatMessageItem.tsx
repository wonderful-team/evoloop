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
  Terminal,
  CheckCircle2,
  Loader2,
  XCircle,
} from "lucide-react"
import { ChangesetInlineHint } from "./ChangesetInlineHint"
import { memo, useState } from "react"
import { motion, AnimatePresence } from "framer-motion"
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
import { MessageContent } from "./MessageContent"
import { VoiceMessage } from "./VoiceMessage"
import { SourcesFooter } from "./SourcesFooter"
import { AgentProcess, AgentProcessStep } from "./AgentProcess"
import { AnalysisResultMessage } from "./AnalysisResultMessage"
import { useShowThinking } from "../UserSettings/AppearanceSettings"
import { TTSButton } from "./TTSButton"
import { useAutoSpeak, useTTS } from "@/hooks/useTTS"
import { useEffect } from "react"
import { cn } from "@evoloop/shared/lib/utils"

// Convert StepItem (from backend steps_snapshot) to AgentProcessStep format
function convertStepsToAgentProcess(steps: Array<{
  id: number
  name: string
  status: string
  type?: string
  time?: string
  details?: string
}>): AgentProcessStep[] {
  return steps
    .filter((step) => {
      const name = step.name || ""
      const tool = name.replace("Using ", "")
      
      // Hide internal steps
      if (step.type === "internal" || tool === "route_to" || name.includes("route_to")) return false
      
      // Define noise patterns (both English raw names and Localized Chinese strings)
      const noisePatterns = [
        "list_directory", "list_files", "read_file", "inspect_task_health",
        "正在列出", "正在读取", "扫描目录", "查找文件", "读取分析"
      ]
      
      const isNoise = noisePatterns.some(p => name.includes(p))
      if (isNoise) return false
      
      return true
    })
    .map((step) => {
      let name = step.name || ""
      let tool = name.replace("Using ", "") || "unknown"
      
      // If tool is still unknown, try to infer it from the name (common in snapshots)
      if (tool === "unknown" && name) {
        if (name.includes("正在读取") || name.includes("read_file")) tool = "read_file"
        else if (name.includes("正在列出") || name.includes("list_directory") || name.includes("list_files")) tool = "list_directory"
        else if (name.includes("正在查找") || name.includes("search_files")) tool = "search_files"
      }

      let input: any = null
      if (step.details) {
        try {
          const detailsJson = JSON.parse(step.details)
          if (detailsJson.input) {
            input = detailsJson.input
          } else if (detailsJson.query || detailsJson.url || detailsJson.path || detailsJson.command) {
            input = {
              query: detailsJson.query,
              url: detailsJson.url,
              path: detailsJson.path,
              command: detailsJson.command,
              target: detailsJson.target,
            }
          }
        } catch (e) {
          // If not JSON, it might be raw text output
        }
      }

      return {
        id: `snap-${step.id}`,
        tool,
        tool_name: step.name,
        input,
        output: step.details || "",
        status: step.status as "success" | "failure" | "running" | "done" | "failed" | "cancelled",
        duration: step.time ? parseFloat(step.time) * 1000 : undefined,
        type: step.type as "node" | "tool" | "ai" | "skill" | undefined,
      }
    })
}

// Unified Tool Execution Section - combines real-time steps and historical snapshot
function ToolExecutionSection({ msg }: { msg: Message }) {
  const { t } = useTranslation()
  const [isOpen, setIsOpen] = useState(false)

  // Combine real-time steps (from SSE) and historical snapshot
  // Prefer real-time steps if available, otherwise use snapshot
  const hasRealtimeSteps = msg.steps && msg.steps.length > 0
  const hasSnapshot = msg.steps_snapshot && msg.steps_snapshot.length > 0

  if (!hasRealtimeSteps && !hasSnapshot) return null

  // Convert snapshot steps to AgentProcessStep format if needed
  const displaySteps: AgentProcessStep[] = hasRealtimeSteps
    ? msg.steps!
    : convertStepsToAgentProcess(msg.steps_snapshot!)
  const isRealtime = hasRealtimeSteps

  // Calculate status counts
  const runningCount = displaySteps.filter((s) => s.status === "running").length
  const completedCount = displaySteps.filter((s) => s.status === "done" || s.status === "success").length
  const failedCount = displaySteps.filter((s) => s.status === "failed" || s.status === "failure").length
  const totalCount = displaySteps.length

  if (totalCount === 0) return null
  let icon = <Terminal className="h-3.5 w-3.5" />
  let statusText = ""

  if (runningCount > 0) {
    icon = <Loader2 className="h-3.5 w-3.5 animate-spin text-primary" />
    statusText = `${t("chat.steps.executing")} ${runningCount}/${totalCount}...`
  } else if (failedCount > 0) {
    icon = <XCircle className="h-3.5 w-3.5 text-destructive" />
    statusText = `${completedCount}/${totalCount} ${t("chat.steps.completed")}, ${failedCount} ${t("chat.steps.failed")}`
  } else {
    icon = <CheckCircle2 className="h-3.5 w-3.5 text-green-500" />
    statusText = `${t("chat.steps.completed")} ${completedCount} ${t("chat.steps.steps")}`
  }

  return (
    <Collapsible open={isOpen} onOpenChange={setIsOpen} className="w-full min-w-0">
      {isOpen ? (
        <AgentProcess
          steps={displaySteps}
          isStreaming={isRealtime && displaySteps.some((s) => s.status === "running")}
          header={
            <CollapsibleTrigger asChild>
              <Button
                variant="ghost"
                size="sm"
                className="h-8 px-3 text-xs text-muted-foreground hover:text-foreground hover:bg-transparent flex items-center gap-2 w-full justify-start rounded-none"
              >
                {icon}
                <span className="font-medium">{statusText}</span>
                <ChevronDown className="h-3.5 w-3.5 ml-auto" />
              </Button>
            </CollapsibleTrigger>
          }
        />
      ) : (
        <CollapsibleTrigger asChild>
          <Button
            variant="ghost"
            size="sm"
            className="h-9 px-3 text-[11px] text-muted-foreground/80 hover:text-foreground bg-muted/30 hover:bg-muted/50 flex items-center gap-2 w-full justify-start rounded-xl border border-border/5 transition-all duration-300 group"
          >
            <div className="flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-background/50 group-hover:bg-background transition-colors">
              {icon}
            </div>
            <span className="font-semibold tracking-tight">{statusText}</span>
            <ChevronRight className={cn("h-3.5 w-3.5 ml-auto opacity-40 transition-transform duration-300", isOpen && "rotate-90")} />
          </Button>
        </CollapsibleTrigger>
      )}
    </Collapsible>
  )
}


export interface Message {
  id: number | string
  role: "human" | "ai" | "tool" | "system"
  content: string
  action_type?: string // Tool output discriminator
  thinking?: string
  timestamp?: string // ISO timestamp from backend
  run_id?: string // Deep Linking
  parent_id?: number // Parent message ID for threading
  node_source?: "chat" | "finish" | "worker" | "supervisor" | "aggregator" | string // 👈 Agent 节点来源，用于语音播报过滤
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
  steps_snapshot?: Array<{
    // Historical task steps
    id: number
    name: string
    status: string
    type?: string
    parent_id?: number // Link to parent phase
    time?: string
    details?: string
  }>
  steps?: AgentProcessStep[] // Tool execution steps
  tool_calls?: any[] // Tool calls for real-time matching
  has_file_operations?: boolean // Whether this message has associated file operations (for Rewind/Retry)
  status?: "pending" | "streaming" | "completed" | "failed" // Message generation status
  // Changeset related (from backend)
  changeset_count: number // Number of files changed in this message (backend provided)
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

    // Render Tool Output as Collapsible accordion
    if (msg.role === "tool") {
      return (
        <div className="flex justify-start mb-2 px-4">
          <Collapsible className="w-full max-w-[85%] sm:max-w-[75%]">
            <CollapsibleTrigger asChild>
              <Button
                variant="ghost"
                size="sm"
                className="h-8 p-0 text-muted-foreground hover:bg-transparent flex items-center gap-2 text-xs w-full justify-start"
              >
                <div className="flex items-center gap-2 p-1.5 bg-muted/50 rounded hover:bg-muted transition-colors">
                  <Bot size={14} className="opacity-70" />
                  <span className="font-mono">{t("chat.messageList.toolExecution")}</span>
                  <ChevronDown size={12} className="opacity-50" />
                </div>
              </Button>
            </CollapsibleTrigger>
            <CollapsibleContent className="mt-2 text-xs font-mono text-muted-foreground bg-muted/30 p-3 rounded-md border-l-2 border-primary/20 overflow-x-auto whitespace-pre-wrap">
              {msg.action_type === "tool_output" || true ? msg.content : "..."}
            </CollapsibleContent>
          </Collapsible>
        </div>
      )
    }

    return (
      <motion.div
        initial={{ opacity: 0, y: 10 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.3 }}
        data-run-id={msg.run_id}
        className={`group relative flex gap-3 ${msg.role === "human" ? "justify-end" : "justify-start"} items-start ${isGrouped ? "mb-1" : "mb-2"} chat-timeline-container`}
      >
        {/* 含蓄的灰度连线 - 仅 AI 消息且非分组的第一条显示 */}
        {msg.role === "ai" && showAvatar && (
          <div className="chat-timeline-line" />
        )}

        {msg.role === "ai" && (
          <div className="shrink-0 w-8 flex flex-col items-center relative z-10">
            {showAvatar ? (
              <Avatar className="h-8 w-8 mt-1 border-none bg-muted shadow-none">
                <AvatarImage src="/bot-avatar.png" />
                <AvatarFallback>
                  <Bot size={16} />
                </AvatarFallback>
              </Avatar>
            ) : (
              <div className="w-8" /> // Spacer for alignment
            )}
          </div>
        )}

        <div className={`relative flex-1 w-0 max-w-[90%] sm:max-w-[85%] min-w-0 flex flex-col gap-1`}>
          
          {/* 1. Action Stream (Thinking + Steps) - AI ONLY, ABOVE Bubble */}
          {msg.role === "ai" && (
            <div className="chat-action-stream empty:hidden animate-in fade-in slide-in-from-top-1 duration-500">
              {/* Reasoning/Thinking Block - Integrated, Always prominent if open */}
              {showThinking && (() => {
                let thinkingContent = msg.thinking
                if (!thinkingContent && msg.content && msg.content.includes("<think>")) {
                  const thinkMatch = msg.content.match(/<think>([\s\S]*?)<\/think>/)
                  if (thinkMatch) {
                    thinkingContent = thinkMatch[1]
                  } else if (msg.content.includes("<think>")) {
                    const parts = msg.content.split("<think>")
                    if (parts.length > 1) thinkingContent = parts[1]
                  }
                }

                if (!thinkingContent) return null

                return (
                  <Collapsible defaultOpen={true} className="w-full">
                    <CollapsibleTrigger asChild>
                      <Button
                        variant="ghost"
                        size="sm"
                        className="h-7 px-2 text-[11px] text-muted-foreground hover:text-foreground hover:bg-muted/50 flex items-center gap-2 w-full justify-start rounded-md"
                      >
                        <Brain className="h-3.5 w-3.5 text-primary/70" />
                        <span className="font-semibold uppercase tracking-wider opacity-70">
                          {t("chat.interface.thinkingProcess")}
                        </span>
                        <ChevronRight className="h-3.5 w-3.5 ml-auto opacity-40 group-data-[state=open]:rotate-90 transition-transform" />
                      </Button>
                    </CollapsibleTrigger>
                    <CollapsibleContent className="text-[11px] leading-relaxed text-muted-foreground/90 bg-primary/5 p-3 rounded-md border-l-2 border-primary/30 whitespace-pre-wrap break-all font-mono mt-1 mb-2">
                      {thinkingContent}
                    </CollapsibleContent>
                  </Collapsible>
                )
              })()}

              {/* Tool Execution Steps */}
              <ToolExecutionSection msg={msg} />
            </div>
          )}

          <div className="flex flex-col gap-1 min-w-0">
            {/* 2. Main Response Bubble */}
            {msg.content && (
              <div className={`rounded-xl px-4 py-3 text-sm leading-relaxed min-w-0 w-fit max-w-full overflow-hidden border ${
                msg.role === "human" 
                  ? "bg-primary text-primary-foreground border-primary/20 ml-auto shadow-none" 
                  : "bg-muted/50 text-foreground border-border/40 mr-auto shadow-none"
              }`}>

                {(() => {
                  // Artifact Detection
                  if (msg.role === "ai") {
                    try {
                      const trimmed = msg.content.trim()
                      if (trimmed.startsWith("{") && trimmed.endsWith("}")) {
                        const obj = JSON.parse(trimmed)
                        if (obj.type === "artifact") {
                          if (obj.artifact_type === "test_report") {
                            return <TestReportCard data={obj.data} />
                          }
                          if (obj.artifact_type === "echarts") {
                            return <EChartsArtifact data={obj.data} />
                          }
                          if (obj.artifact_type === "requirement_analysis") {
                            return (
                              <AnalysisResultMessage
                                analysisId={obj.data.analysis_id}
                                documentId={obj.data.document_id}
                                projectId={obj.data.project_id}
                                data={obj.data.analysis}
                              />
                            )
                          }
                        }
                      }
                    } catch (_e) {
                      // Not JSON
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
                        transcript={voiceAttachment.metadata?.transcript || msg.content !== '[语音消息]' ? msg.content : undefined}
                        isUser={msg.role === "human"}
                      />
                    )
                  }

                  // Strip <think> tags
                  let cleanContent = msg.content
                  if (!msg.thinking && msg.content.includes("<think>")) {
                    cleanContent = msg.content.replace(/<think>[\s\S]*?<\/think>/g, "").trim()
                    if (cleanContent.includes("<think>")) {
                      cleanContent = cleanContent.split("<think>")[0].trim()
                    }
                  }

                  return <MessageContent content={cleanContent} isUser={msg.role === "human"} />
                })()}
              </div>
            )}

            {/* 3. Sources Footer */}
            {msg.role === "ai" && msg.references && msg.references.length > 0 && (
              <SourcesFooter
                references={msg.references.map(ref => ({
                  type: ref.type,
                  name: ref.target_name,
                  path: ref.target_id
                }))}
              />
            )}

            {/* 4. Changeset Inline Hint */}
            {msg.role === "ai" && !!msg.changeset_count && msg.changeset_count > 0 && (
              <ChangesetInlineHint
                fileCount={msg.changeset_count}
                messageId={msg.id}
                onClick={onViewChangeset}
              />
            )}
          </div>

          {/* Message Actions - Flat Buttons */}
          <div className={`absolute ${msg.role === "human" ? "right-full mr-2" : "left-full ml-2"} top-0 opacity-0 group-hover:opacity-100 transition-opacity flex flex-col gap-1`}>
            {/* Exposed Copy Button */}
            <Button
              variant="ghost"
              size="icon"
              className="h-7 w-7 rounded-md bg-background border border-border/40 text-muted-foreground hover:text-foreground"
              onClick={() => navigator.clipboard.writeText(msg.content)}
              title={t("chat.interface.copy")}
            >
              <Copy className="h-3.5 w-3.5" />
            </Button>

            {/* TTS Button */}
            {msg.role === "ai" && msg.content && (
              <TTSButton text={msg.content} size="sm" />
            )}

            {/* Exposed Retry Button */}
            {onRetry && msg.role === "human" && (
              <Button
                variant="ghost"
                size="icon"
                className="h-7 w-7 rounded-md bg-background border border-border/40 text-muted-foreground hover:text-foreground"
                onClick={() => onRetry(msg)}
                title={t("chat.interface.retry")}
              >
                <RotateCcw className="h-3.5 w-3.5" />
              </Button>
            )}

            <DropdownMenu>
              <DropdownMenuTrigger asChild>
                <Button
                  variant="ghost"
                  size="icon"
                  className="h-7 w-7 rounded-md bg-background border border-border/40"
                >
                  <MoreHorizontal className="h-3.5 w-3.5" />
                </Button>
              </DropdownMenuTrigger>
              <DropdownMenuContent align={msg.role === "human" ? "end" : "start"}>
                {msg.role === "ai" && onAddToMemory && (
                  <DropdownMenuItem onClick={() => onAddToMemory(msg.content)}>
                    <Brain className="mr-2 h-4 w-4" />{" "}
                    {t("chat.interface.memorize")}
                  </DropdownMenuItem>
                )}
                {onRewind && msg.role === "human" && (
                  <DropdownMenuItem onClick={() => onRewind(msg)}>
                    <Undo className="mr-2 h-4 w-4" />{" "}
                    {t("chat.interface.rewind")}
                  </DropdownMenuItem>
                )}
                {onQuote && (
                  <DropdownMenuItem onClick={() => onQuote()}>
                    <Quote className="mr-2 h-4 w-4" />{" "}
                    {t("chat.interface.quote")}
                  </DropdownMenuItem>
                )}
              </DropdownMenuContent>
            </DropdownMenu>
          </div>
        </div>

        {msg.role === "human" && (
          <div className="shrink-0 w-8 flex flex-col items-center">
            {showAvatar ? (
              <Avatar className="h-8 w-8 mt-1 border-none bg-primary/10">
                <AvatarFallback>
                  <User size={16} className="text-primary" />
                </AvatarFallback>
              </Avatar>
            ) : (
              <div className="w-8" /> // Spacer
            )}
          </div>
        )}

        {/* Timestamp */}
        {msg.timestamp && (
          <div className={`absolute -bottom-4 ${msg.role === "human" ? "right-12" : "left-12"} text-[10px] text-muted-foreground/40 font-mono`}>
            {new Date(msg.timestamp).toLocaleTimeString([], {
              hour: "2-digit",
              minute: "2-digit",
            })}
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
      prevProps.msg.steps === nextProps.msg.steps
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
