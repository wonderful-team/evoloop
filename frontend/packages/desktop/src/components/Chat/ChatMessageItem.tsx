import {
  Bot,
  Brain,
  ChevronDown,
  Copy,
  MoreHorizontal,
  RotateCcw,
  User,
  Quote,
} from "lucide-react"
import { memo } from "react"
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


export interface Message {
  id: number | string
  role: "user" | "ai" | "tool" | "system"
  content: string
  action_type?: string // Phase 17: Tool Output Refactor
  thinking?: string
  timestamp?: string // ISO timestamp from backend
  run_id?: string // Deep Linking
  parent_id?: number // Phase 8: Threading
  references?: Array<{ // Phase 9: Persistent References
    id: string
    type: string // memory, file, knowledge
    target_id: string
    target_name: string
  }>
  originalType?: string // Kept for filtering
  steps_snapshot?: Array<{
    // Phase 6: Historical task steps
    id: number
    name: string
    status: string
    type?: string
    time?: string
    details?: string
  }>
  steps?: AgentProcessStep[] // Phase 24: Tool Execution Steps
  tool_calls?: any[] // Phase 24: For Real-Time matching
}

interface ChatMessageItemProps {
  msg: Message
  isGrouped?: boolean
  showAvatar?: boolean
  onAddToMemory?: (text: string) => void
  onRewind?: () => void
  onRetry?: () => void
  onQuote?: () => void
}

const ChatMessageItem = memo(
  ({ msg, isGrouped, showAvatar, onAddToMemory, onRewind, onRetry, onQuote }: ChatMessageItemProps) => {
    const { t } = useTranslation()

    // Hide system prompts from main chat
    if (msg.role === "system") {
      return null
    }

    // Phase 17: Render Tool Output as Collapsible
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
      <div data-run-id={msg.run_id} className={`group relative flex gap-3 ${msg.role === "user" ? "justify-end" : "justify-start"} items-start ${isGrouped ? "mb-1" : "mb-1"}`}>
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

            {/* Reasoning/Thinking Block (Historical or Streaming) */}
            {(() => {
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

              const isStreaming = !msg.thinking && !!msg.content && msg.content.includes("<think>")
              if (!thinkingContent) return null

              return (
                <Collapsible defaultOpen={isStreaming} className="w-full">
                  <CollapsibleTrigger asChild>
                    <Button
                      variant="ghost"
                      size="sm"
                      className="h-6 p-0 text-muted-foreground hover:bg-transparent flex items-center gap-1 text-xs"
                    >
                      <Brain size={12} />
                      <span className="italic">
                        {t("chat.interface.thinkingProcess", "Reasoning Process")}
                      </span>
                      <ChevronDown size={12} className="opacity-50" />
                    </Button>
                  </CollapsibleTrigger>
                  <CollapsibleContent className="text-xs text-muted-foreground bg-muted/30 p-2 rounded-md mb-2 border-l-2 border-primary/20 whitespace-pre-wrap font-mono">
                    {thinkingContent}
                  </CollapsibleContent>
                </Collapsible>
              )
            })()}

            {/* Tool Execution Process (Collapsible) */}
            {/* Historical Task Steps (Unified Component) */}
            {msg.steps_snapshot && msg.steps_snapshot.length > 0 && (
              <div className="mb-2 w-full">
                <ExecutionSteps steps={msg.steps_snapshot as any} />
              </div>
            )}

            {/* Sources Footer */}
            {msg.role === "ai" && msg.references && msg.references.length > 0 && (
              <SourcesFooter
                references={msg.references.map(ref => ({
                  type: ref.type,
                  name: ref.target_name,
                  path: ref.target_id
                }))}
              />
            )}

            {/* Main Content */}
            {(msg.content || !msg.thinking || (msg.steps && msg.steps.length > 0)) && (
              <div className={`rounded-lg px-4 py-3 text-sm leading-relaxed ${msg.role === "user" ? "bg-primary text-primary-foreground" : "bg-muted text-foreground"}`}>

                {(() => {
                  // Artifact Detection
                  if (msg.role === "ai") {
                    try {
                      const trimmed = msg.content.trim()
                      if (trimmed.startsWith("{") && trimmed.endsWith("}")) {
                        const obj = JSON.parse(trimmed)
                        if (
                          obj.type === "artifact" &&
                          obj.artifact_type === "test_report"
                        ) {
                          return <TestReportCard data={obj.data} />
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
                  return (
                    <div className="flex flex-col gap-2">
                      <MessageContent content={cleanContent} />
                      {/* Tool Execution Process (Collapsible) - Embedded at bottom */}
                      {msg.steps && msg.steps.length > 0 && (
                        <div className="mt-2">
                          <AgentProcess
                            steps={msg.steps}
                            isStreaming={msg.steps.some((s) => s.status === "running")}
                          />
                        </div>
                      )}
                    </div>
                  )
                })()}
              </div>
            )}
          </div>

          {/* Message Actions */}
          <div className={`absolute ${msg.role === "user" ? "left-2 top-2" : "right-2 top-2"} opacity-0 group-hover:opacity-100 transition-opacity flex gap-1`}>
            {/* Exposed Retry Button for AI */}
            {onRetry && (
              <Button
                variant="ghost"
                size="icon"
                className="h-8 w-8 rounded-full bg-background border shadow-sm text-muted-foreground hover:text-foreground"
                onClick={() => onRetry()}
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
                <DropdownMenuItem
                  onClick={() => navigator.clipboard.writeText(msg.content)}
                >
                  <Copy className="mr-2 h-4 w-4" /> {t("chat.interface.copy")}
                </DropdownMenuItem>
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
                    {onRewind && (
                      <DropdownMenuItem onClick={() => onRewind()}>
                        <RotateCcw className="mr-2 h-4 w-4" />{" "}
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
                  </>
                )}
              </DropdownMenuContent>
            </DropdownMenu>
          </div>
        </div>

        {msg.role === "user" && (
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
          <div className={`absolute -bottom-0 ${msg.role === "user" ? "right-0" : "left-0"} text-[10px] text-muted-foreground/60`}>
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
