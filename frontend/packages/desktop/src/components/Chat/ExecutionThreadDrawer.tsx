import { Badge } from "@evoloop/shared/components/ui/badge"
import {
  Sheet,
  SheetContent,
  SheetHeader,
  SheetTitle,
} from "@evoloop/shared/components/ui/sheet"
import { Loader2, MessageSquare, Wrench } from "lucide-react"
import { useEffect, useState } from "react"
import { useTranslation } from "react-i18next"
import { ConversationsService } from "@/client"
import { normalizeMessage } from "@/stores/chat/helpers"

interface ExecutionThreadDrawerProps {
  open: boolean
  threadId: string
  title?: string
  onClose: () => void
}

/** 轻量执行抽屉：渲染值守执行线程（wakeup_*）的消息时间线（只读）。 */
export const ExecutionThreadDrawer = ({
  open,
  threadId,
  title,
  onClose,
}: ExecutionThreadDrawerProps) => {
  const { t } = useTranslation()
  const [messages, setMessages] = useState<any[]>([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (!open || !threadId) return
    let cancelled = false
    setLoading(true)
    setError(null)
    setMessages([])
    ConversationsService.getConversationMessages({ threadId, limit: 50 })
      .then((data: any) => {
        if (cancelled) return
        const msgs = (data.data || [])
          .map(normalizeMessage)
          .sort(
            (a: any, b: any) =>
              (a.sequence_number ?? 0) - (b.sequence_number ?? 0) ||
              new Date(a.timestamp || 0).getTime() -
                new Date(b.timestamp || 0).getTime(),
          )
        setMessages(msgs)
      })
      .catch((e: unknown) => {
        if (!cancelled)
          setError(
            e instanceof Error
              ? e.message
              : String(e).slice(0, 160) || "加载失败",
          )
      })
      .finally(() => {
        if (!cancelled) setLoading(false)
      })
    return () => {
      cancelled = true
    }
  }, [open, threadId])

  return (
    <Sheet open={open} onOpenChange={(o) => !o && onClose()}>
      <SheetContent
        side="right"
        className="flex w-[460px] flex-col gap-0 p-0 sm:max-w-[460px]"
      >
        <SheetHeader className="border-b border-border/60 px-4 py-3">
          <SheetTitle className="flex items-center gap-2 text-sm font-semibold">
            <MessageSquare className="h-4 w-4 text-muted-foreground" />
            {title || t("chat.executionThread.title", "执行会话")}
          </SheetTitle>
          <p className="truncate font-mono text-[10px] text-muted-foreground">
            {threadId}
          </p>
        </SheetHeader>
        <div className="flex-1 overflow-y-auto px-4 py-3">
          {loading && (
            <div className="flex h-24 items-center justify-center gap-2 text-sm text-muted-foreground">
              <Loader2 className="h-4 w-4 animate-spin" />
              {t("chat.executionThread.loading", "加载执行记录…")}
            </div>
          )}
          {!loading && error && (
            <div className="rounded-md bg-destructive/10 px-3 py-2 text-xs text-destructive">
              {error}
            </div>
          )}
          {!loading && !error && messages.length === 0 && (
            <div className="py-10 text-center text-xs text-muted-foreground">
              {t("chat.executionThread.empty", "该线程暂无消息")}
            </div>
          )}
          <div className="flex flex-col gap-3">
            {messages.map((m: any) => (
              <div
                key={String(m.id)}
                className="rounded-lg border border-border/50 bg-muted/30 px-3 py-2"
              >
                <div className="mb-1 flex items-center gap-2">
                  <Badge
                    variant={m.role === "human" ? "default" : "secondary"}
                    className="h-4 px-1.5 text-[9px]"
                  >
                    {m.role === "tool" && (
                      <Wrench className="mr-0.5 inline h-2.5 w-2.5" />
                    )}
                    {m.tool_name || m.role}
                  </Badge>
                  {m.timestamp && (
                    <span className="text-[9px] text-muted-foreground">
                      {new Date(m.timestamp).toLocaleTimeString()}
                    </span>
                  )}
                </div>
                {m.content ? (
                  <p className="whitespace-pre-wrap break-words text-xs leading-relaxed text-foreground/90">
                    {m.content.length > 1200
                      ? `${m.content.slice(0, 1200)}…`
                      : m.content}
                  </p>
                ) : null}
              </div>
            ))}
          </div>
        </div>
      </SheetContent>
    </Sheet>
  )
}
