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
import { memo, useState } from "react"
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
import { MessageContent } from "./MessageContent"
import { ExecutionSteps } from "./ExecutionSteps"
import { SourcesFooter } from "./SourcesFooter"
import { AgentProcess, AgentProcessStep } from "./AgentProcess"
import { AnalysisResultMessage } from "./AnalysisResultMessage"
import { useShowThinking } from "../UserSettings/AppearanceSettings"

// Unified Tool Execution Section - combines real-time steps and historical snapshot
function ToolExecutionSection({ msg }: { msg: Message }) {
  const { t } = useTranslation()
  const [isOpen, setIsOpen] = useState(false)

  // Combine real-time steps (from SSE) and historical snapshot
  // Prefer real-time steps if available, otherwise use snapshot
  const hasRealtimeSteps = msg.steps && msg.steps.length > 0
  const hasSnapshot = msg.steps_snapshot && msg.steps_snapshot.length > 0

  if (!hasRealtimeSteps && !hasSnapshot) return null

  // Determine which steps to display
  const displaySteps = hasRealtimeSteps ? msg.steps! : msg.steps_snapshot!
  const isRealtime = hasRealtimeSteps

  // Calculate status counts
  const runningCount = displaySteps.filter((s) => s.status === "running").length
  const completedCount = displaySteps.filter((s) => s.status === "done" || s.status === "success").length
  const failedCount = displaySteps.filter((s) => s.status === "failed" || s.status === "failure").length
  const totalCount = displaySteps.length

  // Determine icon and text based on status
  let icon = <Terminal className="h-3.5 w-3.5" />
  let statusText = ""

  if (runningCount > 0) {
    icon = <Loader2 className="h-3.5 w-3.5 animate-spin text-primary" />
    statusText = `${t("chat.steps.executing", "Executing")} ${runningCount}/${totalCount}...`
  } else if (failedCount > 0) {
    icon = <XCircle className="h-3.5 w-3.5 text-destructive" />
    statusText = `${completedCount}/${totalCount} ${t("chat.steps.completed", "completed")}, ${failedCount} ${t("chat.steps.failed", "failed")}`
  } else {
    icon = <CheckCircle2 className="h-3.5 w-3.5 text-green-500" />
    statusText = `${t("chat.steps.completed", "Completed")} ${completedCount} ${t("chat.steps.steps", "steps")}`
  }

  return (
    <Collapsible open={isOpen} onOpenChange={setIsOpen} className="w-full">
      <CollapsibleTrigger asChild>
        <Button
          variant="ghost"
          size="sm"
          className="h-7 px-2 text-xs text-muted-foreground hover:text-foreground hover:bg-muted/50 flex items-center gap-2 w-full justify-start"
        >
          {icon}
          <span className="font-medium">{statusText}</span>
          {isOpen ? (
            <ChevronDown className="h-3.5 w-3.5 ml-auto" />
          ) : (
            <ChevronRight className="h-3.5 w-3.5 ml-auto" />
          )}
        </Button>
      </CollapsibleTrigger>
      <CollapsibleContent className="mt-1">
        {isRealtime ? (
          // Real-time steps use AgentProcess for richer display
          <AgentProcess
            steps={msg.steps!}
            isStreaming={msg.steps!.some((s) => s.status === "running")}
          />
        ) : (
          // Historical snapshot uses ExecutionSteps
          <ExecutionSteps steps={msg.steps_snapshot as any} />
        )}
      </CollapsibleContent>
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
  references?: Array<{ // Persistent message references
    id: string
    type: string // memory, file, knowledge
    target_id: string
    target_name: string
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
}

interface ChatMessageItemProps {
  msg: Message
  isGrouped?: boolean
  showAvatar?: boolean
  onAddToMemory?: (text: string) => void
  onRewind?: (msg: Message) => void
  onRetry?: (msg: Message) => void
  onQuote?: () => void
}

const ChatMessageItem = memo(
  ({ msg, isGrouped, showAvatar, onAddToMemory, onRewind, onRetry, onQuote }: ChatMessageItemProps) => {
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
          <Collapsible className="w-full max-w-3xl">
            <CollapsibleTrigger asChild>
              <Button
                variant="ghost"
                size="sm"
                className="h-8 p-0 text-muted-foreground hover:bg-transparent flex items-center gap-2 text-xs w-full justify-start"
              >
                <div className="flex items-center gap-2 p-1.5 bg-muted/50 rounded hover:bg-muted transition-colors">
                  <Bot size={14} className="opacity-70" />
                  <span className="font-mono">{t("chat.messageList.toolExecution", "Tool Output")}</span>
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
      <div data-run-id={msg.run_id} className={`group relative flex gap-3 ${msg.role === "human" ? "justify-end" : "justify-start"} items-start ${isGrouped ? "mb-1" : "mb-1"}`}>
        {msg.role === "ai" && (
          <div className="shrink-0 w-8 flex flex-col items-center">
            {showAvatar ? (
              <Avatar className="h-8 w-8 mt-1">
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

        <div className={`relative flex-1 max-w-full`}>
          <div className="flex flex-col gap-1">

            {/* 1. Main Content - AI FIRST */}
            {msg.content && (
              <div className={`rounded-lg px-4 py-3 text-sm leading-relaxed ${msg.role === "human" ? "bg-primary text-primary-foreground" : "bg-muted text-foreground"}`}>

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
                      // Not JSON, fall through
                    }
                  }

                  // Strip <think> tags for display if they were extracted above
                  let cleanContent = msg.content
                  if (!msg.thinking && msg.content.includes("<think>")) {
                    cleanContent = msg.content.replace(/<think>[\s\S]*?<\/think>/g, "").trim()
                    // Also handle open tag case for streaming
                    if (cleanContent.includes("<think>")) {
                      cleanContent = cleanContent.split("<think>")[0].trim()
                    }
                  }

                  // Standard Markdown Render
                  return <MessageContent content={cleanContent} isUser={msg.role === "human"} />
                })()}
              </div>
            )}

            {/* 2. Sources Footer */}
            {msg.role === "ai" && msg.references && msg.references.length > 0 && (
              <SourcesFooter
                references={msg.references.map(ref => ({
                  type: ref.type,
                  name: ref.target_name,
                  path: ref.target_id
                }))}
              />
            )}

            {/* 3. Reasoning/Thinking Block - Collapsed by default */}
            {showThinking && (() => {
              // 1. Use persisted thinking if available
              let thinkingContent = msg.thinking

              // 2. Or fallback to parsing from content (for streaming)
              if (!thinkingContent && msg.content && msg.content.includes("<think>")) {
                const thinkMatch = msg.content.match(/<think>([\s\S]*?)<\/think>/)
                if (thinkMatch) {
                  thinkingContent = thinkMatch[1]
                } else if (msg.content.includes("<think>")) {
                  // Streaming incomplete tag? or open tag
                  const parts = msg.content.split("<think>")
                  if (parts.length > 1) {
                    thinkingContent = parts[1] // Show incomplete thinking
                  }
                }
              }

              if (!thinkingContent) return null

              return (
                <Collapsible defaultOpen={false} className="w-full">
                  <CollapsibleTrigger asChild>
                    <Button
                      variant="ghost"
                      size="sm"
                      className="h-7 px-2 text-xs text-muted-foreground hover:text-foreground hover:bg-muted/50 flex items-center gap-2 w-full justify-start"
                    >
                      <Brain className="h-3.5 w-3.5" />
                      <span className="font-medium">
                        {t("chat.interface.thinkingProcess", "Reasoning Process")}
                      </span>
                      <ChevronRight className="h-3.5 w-3.5 ml-auto" />
                    </Button>
                  </CollapsibleTrigger>
                  <CollapsibleContent className="text-xs text-muted-foreground bg-muted/30 p-2 rounded-md border-l-2 border-primary/20 whitespace-pre-wrap font-mono">
                    {thinkingContent}
                  </CollapsibleContent>
                </Collapsible>
              )
            })()}

            {/* 4. Tool Execution Steps - Unified Display */}
            <ToolExecutionSection msg={msg} />
          </div>

          {/* Message Actions - Bottom of bubble, keep left/right position */}
          <div className={`absolute ${msg.role === "human" ? "left-0" : "right-0"} -bottom-3 opacity-0 group-hover:opacity-100 transition-opacity flex gap-1`}>
            {/* Exposed Copy Button - For all message types */}
            <Button
              variant="ghost"
              size="icon"
              className="h-8 w-8 rounded-full bg-background border shadow-sm text-muted-foreground hover:text-foreground"
              onClick={() => navigator.clipboard.writeText(msg.content)}
              title={t("chat.interface.copy", "Copy")}
            >
              <Copy className="h-4 w-4" />
            </Button>

            {/* Exposed Retry Button - Only for user messages */}
            {onRetry && msg.role === "human" && (
              <Button
                variant="ghost"
                size="icon"
                className="h-8 w-8 rounded-full bg-background border shadow-sm text-muted-foreground hover:text-foreground"
                onClick={() => onRetry(msg)}
                title={t("chat.interface.retry", "Retry")}
              >
                <RotateCcw className="h-4 w-4" />
              </Button>
            )}

            <DropdownMenu>
              <DropdownMenuTrigger asChild>
                <Button
                  variant="ghost"
                  size="icon"
                  className="h-8 w-8 rounded-full bg-background border shadow-sm"
                >
                  <MoreHorizontal className="h-4 w-4" />
                </Button>
              </DropdownMenuTrigger>
              <DropdownMenuContent>
                {msg.role === "ai" && (
                  <>
                    {onAddToMemory && (
                      <DropdownMenuItem
                        onClick={() => onAddToMemory(msg.content)}
                      >
                        <Brain className="mr-2 h-4 w-4" />{" "}
                        {t("chat.interface.memorize")}
                      </DropdownMenuItem>
                    )}
                  </>
                )}
                {/* Rewind Action - Only for user messages */}
                {onRewind && msg.role === "human" && (
                  <DropdownMenuItem onClick={() => onRewind(msg)}>
                    <Undo className="mr-2 h-4 w-4" />{" "}
                    {t("chat.interface.rewind")}
                  </DropdownMenuItem>
                )}
                {/* Quote Action */}
                {onQuote && (
                  <DropdownMenuItem onClick={() => onQuote()}>
                    <Quote className="mr-2 h-4 w-4" />{" "}
                    {t("chat.interface.quote", "Quote")}
                  </DropdownMenuItem>
                )}
              </DropdownMenuContent>
            </DropdownMenu>
          </div>
        </div>

        {msg.role === "human" && (
          <div className="shrink-0 w-8 flex flex-col items-center">
            {showAvatar ? (
              <Avatar className="h-8 w-8 mt-1">
                <AvatarFallback>
                  <User size={16} />
                </AvatarFallback>
              </Avatar>
            ) : (
              <div className="w-8" /> // Spacer
            )}
          </div>
        )}

        {/* Timestamp */}
        {msg.timestamp && (
          <div className={`absolute -bottom-0 ${msg.role === "human" ? "right-0" : "left-0"} text-[10px] text-muted-foreground/60`}>
            {new Date(msg.timestamp).toLocaleTimeString([], {
              hour: "2-digit",
              minute: "2-digit",
            })}
          </div>
        )}
      </div>
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

export { ChatMessageItem }
