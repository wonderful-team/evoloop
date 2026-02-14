import {
    Bot,
    User,
    MoreHorizontal,
    Copy,
    Quote,
    AlertTriangle
} from "lucide-react"
import { useTranslation } from "react-i18next"
import { cn } from "@evoloop/shared"
import { Button } from "@evoloop/shared/components/ui/button"
import { Avatar, AvatarFallback, AvatarImage } from "@evoloop/shared/components/ui/avatar"
import {
    DropdownMenu,
    DropdownMenuContent,
    DropdownMenuItem,
    DropdownMenuTrigger,
} from "@evoloop/shared/components/ui/dropdown-menu"
import { toast } from "sonner"
import { RichContent } from "./RichContent"
import { ThinkingBlock } from "./ThinkingBlock"
import { MobileHumanRequestCard } from "./MobileHumanRequestCard"
import type { LogMessage } from "../../hooks/useEvoLoopWebSocket"

export function StarterButton({
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

export function DateSeparator({ date }: { date: string }) {
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

interface MessageItemProps {
    msg: LogMessage
    onHITLResponse?: (threadId: string, response: string, commandId?: number) => void
    isGrouped?: boolean
    showAvatar?: boolean
}

export function MessageItem({
    msg,
    onHITLResponse,
    isGrouped,
    showAvatar
}: MessageItemProps) {
    const { t } = useTranslation()

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
            <ThinkingBlock
                content={msg.content}
                timestamp={msg.timestamp}
                isComplete={true}
            />
        )
    }

    if (msg.type === "tool" || msg.type === "output") {
        return (
            <div className="mb-2 p-2 bg-muted/20 border rounded text-xs font-mono break-all">
                <span className="font-bold opacity-50 uppercase mr-2">{msg.type}:</span>
                {JSON.stringify(msg.content)}
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
        const requestData = typeof msg.content === "string" ? JSON.parse(msg.content) : msg.content

        return (
            <div className="flex flex-col mb-4 animate-in slide-in-from-left-2 fade-in duration-300 max-w-[95%]">
                <MobileHumanRequestCard
                    request={requestData}
                    onRespond={(response) => {
                        if (onHITLResponse && msg.thread_id) {
                            onHITLResponse(msg.thread_id, response, (msg as any).log_id)
                        }
                    }}
                />
            </div>
        )
    }

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
                {(showAvatar && (msg.type === "ai" || msg.type === "model")) ? (
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
                        <MessageItem
                            msg={{ ...msg, type: "thought", content: thinking }}
                            isGrouped={false}
                            showAvatar={false}
                        />
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
