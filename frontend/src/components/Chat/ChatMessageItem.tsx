
import { memo } from "react"
import { useTranslation } from "react-i18next"
import { Bot, User, Brain, ChevronDown, MoreHorizontal, Copy, Save, RotateCcw } from "lucide-react"
import { Avatar, AvatarFallback, AvatarImage } from "../ui/avatar"
import { Button } from "../ui/button"
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from "@/components/ui/collapsible"
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuTrigger } from "@/components/ui/dropdown-menu"
import { MessageContent } from "./MessageContent"
import { TestReportCard } from "./Artifacts/TestReportCard"

export interface Message {
    id: number | string
    role: "user" | "ai"
    content: string
    thinking?: string
    timestamp?: string  // ISO timestamp from backend
}

interface ChatMessageItemProps {
    msg: Message
    onAddToMemory?: (text: string) => void
    onExport?: (text: string) => void
    onRewind?: () => void
}

const ChatMessageItem = memo(({ msg, onAddToMemory, onExport, onRewind }: ChatMessageItemProps) => {
    const { t } = useTranslation()

    return (
        <div className={`group relative flex gap-3 ${msg.role === 'user' ? 'justify-end' : 'justify-start'} items-start mb-4`}>
            {msg.role === 'ai' && (
                <Avatar className="h-8 w-8 mt-1 shrink-0">
                    <AvatarImage src="/bot-avatar.png" />
                    <AvatarFallback><Bot size={16} /></AvatarFallback>
                </Avatar>
            )}

            <div className={`relative max-w-[85%]`}>
                <div className="flex flex-col gap-1">
                    {/* Reasoning/Thinking Block */}
                    {msg.thinking && (
                        <Collapsible defaultOpen={false} className="w-full">
                            <CollapsibleTrigger asChild>
                                <Button variant="ghost" size="sm" className="h-6 p-0 text-muted-foreground hover:bg-transparent flex items-center gap-1 text-xs">
                                    <Brain size={12} />
                                    <span className="italic">{t('chat.interface.thinkingProcess', "Reasoning Process")}</span>
                                    <ChevronDown size={12} className="opacity-50" />
                                </Button>
                            </CollapsibleTrigger>
                            <CollapsibleContent className="text-xs text-muted-foreground bg-muted/30 p-2 rounded-md mb-2 border-l-2 border-primary/20 whitespace-pre-wrap">
                                {msg.thinking}
                            </CollapsibleContent>
                        </Collapsible>
                    )}

                    {/* Main Content */}
                    {(msg.content || !msg.thinking) && (
                        <div className={`rounded-lg px-4 py-3 text-sm leading-relaxed ${msg.role === 'user' ? 'bg-primary text-primary-foreground' : 'bg-muted text-foreground'}`}>
                            {(() => {
                                // Artifact Detection
                                if (msg.role === 'ai') {
                                    try {
                                        const trimmed = msg.content.trim();
                                        if (trimmed.startsWith('{') && trimmed.endsWith('}')) {
                                            const obj = JSON.parse(trimmed);
                                            if (obj.type === "artifact" && obj.artifact_type === "test_report") {
                                                return <TestReportCard data={obj.data} />
                                            }
                                        }
                                    } catch (e) {
                                        // Not JSON, fall through
                                    }
                                }

                                // Standard Markdown Render
                                return <MessageContent content={msg.content} />
                            })()}
                        </div>
                    )}
                </div>

                {/* Message Actions */}
                <div className={`absolute -top-2 ${msg.role === 'user' ? '-left-10' : '-right-10'} opacity-0 group-hover:opacity-100 transition-opacity`}>
                    <DropdownMenu>
                        <DropdownMenuTrigger asChild>
                            <Button variant="ghost" size="icon" className="h-8 w-8 rounded-full bg-background border shadow-sm">
                                <MoreHorizontal className="h-4 w-4" />
                            </Button>
                        </DropdownMenuTrigger>
                        <DropdownMenuContent>
                            <DropdownMenuItem onClick={() => navigator.clipboard.writeText(msg.content)}>
                                <Copy className="mr-2 h-4 w-4" /> {t('chat.interface.copy')}
                            </DropdownMenuItem>
                            {msg.role === 'ai' && (
                                <>
                                    {onAddToMemory && (
                                        <DropdownMenuItem onClick={() => onAddToMemory(msg.content)}>
                                            <Brain className="mr-2 h-4 w-4" /> {t('chat.interface.memorize')}
                                        </DropdownMenuItem>
                                    )}
                                    {onExport && (
                                        <DropdownMenuItem onClick={() => onExport(msg.content)}>
                                            <Save className="mr-2 h-4 w-4" /> {t('chat.interface.export')}
                                        </DropdownMenuItem>
                                    )}
                                    {onRewind && (
                                        <DropdownMenuItem onClick={() => onRewind()}>
                                            <RotateCcw className="mr-2 h-4 w-4" /> {t('chat.interface.rewind')}
                                        </DropdownMenuItem>
                                    )}
                                </>
                            )}
                        </DropdownMenuContent>
                    </DropdownMenu>
                </div>
            </div>

            {msg.role === 'user' && (
                <Avatar className="h-8 w-8 mt-1 shrink-0">
                    <AvatarFallback><User size={16} /></AvatarFallback>
                </Avatar>
            )}

            {/* Timestamp */}
            {msg.timestamp && (
                <div className={`absolute -bottom-4 ${msg.role === 'user' ? 'right-0' : 'left-10'} text-[10px] text-muted-foreground/60`}>
                    {new Date(msg.timestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
                </div>
            )}
        </div>
    )
}, (prevProps, nextProps) => {
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
})

ChatMessageItem.displayName = "ChatMessageItem"

export { ChatMessageItem }
