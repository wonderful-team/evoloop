import {
  Bot,
  Brain,
  ChevronDown,
  Copy,
  MoreHorizontal,
  RotateCcw,
  Save,
  User,
} from "lucide-react"
import { memo } from "react"
import { useTranslation } from "react-i18next"
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from "@/components/ui/collapsible"
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu"
import { Avatar, AvatarFallback, AvatarImage } from "../ui/avatar"
import { Button } from "../ui/button"
import { TestReportCard } from "./Artifacts/TestReportCard"
import { MessageContent } from "./MessageContent"
import { SourcesFooter } from "./SourcesFooter"

export interface Message {
  id: number | string
  role: "user" | "ai" | "tool" | "system"
  content: string
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
  tasks_snapshot?: Array<{
    // Phase 6: Historical task steps
    id: number
    name: string
    status: string
    type?: string
    time?: string
    details?: string
  }>
}

interface ChatMessageItemProps {
  msg: Message
  onAddToMemory?: (text: string) => void
  onExport?: (text: string) => void
  onRewind?: () => void
}

const ChatMessageItem = memo(
  ({ msg, onAddToMemory, onExport, onRewind }: ChatMessageItemProps) => {
    const { t } = useTranslation()

    // Hide intermediate tool outputs and system prompts from main chat
    if (msg.role === "tool" || msg.role === "system") {
      return null
    }

    return (
      <div
        data-run-id={msg.run_id}
        className={`group relative flex gap-3 ${msg.role === "user" ? "justify-end" : "justify-start"} items-start mb-4`}
      >
        {msg.role === "ai" && (
          <Avatar className="h-8 w-8 mt-1 shrink-0">
            <AvatarImage src="/bot-avatar.png" />
            <AvatarFallback>
              <Bot size={16} />
            </AvatarFallback>
          </Avatar>
        )}

        <div className={`relative max-w-[85%]`}>
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

            {/* Phase 6: Historical Task Steps */}
            {msg.tasks_snapshot && msg.tasks_snapshot.length > 0 && (
              <Collapsible defaultOpen={false} className="w-full">
                <CollapsibleTrigger asChild>
                  <Button
                    variant="ghost"
                    size="sm"
                    className="h-6 p-0 text-muted-foreground hover:bg-transparent flex items-center gap-1 text-xs"
                  >
                    <ChevronDown size={12} />
                    <span className="italic">
                      {
                        msg.tasks_snapshot.filter((t) => t.status === "done")
                          .length
                      }
                      /{msg.tasks_snapshot.length} steps
                    </span>
                  </Button>
                </CollapsibleTrigger>
                <CollapsibleContent className="text-xs text-muted-foreground bg-muted/30 p-2 rounded-md mb-2 border-l-2 border-primary/20">
                  <ul className="space-y-1">
                    {msg.tasks_snapshot.map((t) => (
                      <li key={t.id} className="flex items-center gap-2">
                        <span
                          className={
                            t.status === "done"
                              ? "text-green-500"
                              : t.status === "failed"
                                ? "text-red-500"
                                : "text-muted-foreground"
                          }
                        >
                          •
                        </span>
                        <span>{t.name}</span>
                        {t.time && (
                          <span className="text-muted-foreground/60">
                            ({t.time})
                          </span>
                        )}
                      </li>
                    ))}
                  </ul>
                </CollapsibleContent>
              </Collapsible>
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
            {(msg.content || !msg.thinking) && (
              <div
                className={`rounded-lg px-4 py-3 text-sm leading-relaxed ${msg.role === "user" ? "bg-primary text-primary-foreground" : "bg-muted text-foreground"}`}
              >
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
                  return <MessageContent content={cleanContent} />
                })()}
              </div>
            )}
          </div>

          {/* Message Actions */}
          <div
            className={`absolute -top-2 ${msg.role === "user" ? "-left-10" : "-right-10"} opacity-0 group-hover:opacity-100 transition-opacity`}
          >
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
                    {onExport && (
                      <DropdownMenuItem onClick={() => onExport(msg.content)}>
                        <Save className="mr-2 h-4 w-4" />{" "}
                        {t("chat.interface.export")}
                      </DropdownMenuItem>
                    )}
                    {onRewind && (
                      <DropdownMenuItem onClick={() => onRewind()}>
                        <RotateCcw className="mr-2 h-4 w-4" />{" "}
                        {t("chat.interface.rewind")}
                      </DropdownMenuItem>
                    )}
                  </>
                )}
              </DropdownMenuContent>
            </DropdownMenu>
          </div>
        </div>

        {msg.role === "user" && (
          <Avatar className="h-8 w-8 mt-1 shrink-0">
            <AvatarFallback>
              <User size={16} />
            </AvatarFallback>
          </Avatar>
        )}

        {/* Timestamp */}
        {msg.timestamp && (
          <div
            className={`absolute -bottom-4 ${msg.role === "user" ? "right-0" : "left-10"} text-[10px] text-muted-foreground/60`}
          >
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
      prevProps.msg.thinking === nextProps.msg.thinking
    )
  },
)

ChatMessageItem.displayName = "ChatMessageItem"

export { ChatMessageItem }
