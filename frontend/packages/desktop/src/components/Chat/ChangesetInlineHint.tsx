import { FileDiff, ChevronRight } from "lucide-react"
import { useTranslation } from "react-i18next"
import { cn } from "@evoloop/shared/lib/utils"
import { useChatStore } from "@/stores/chatStore"

interface ChangesetInlineHintProps {
  fileCount: number
  messageId?: string | number  // Message ID to check viewed status
  onClick?: () => void
  className?: string
}

export function ChangesetInlineHint({
  fileCount,
  messageId,
  onClick,
  className,
}: ChangesetInlineHintProps) {
  const { t } = useTranslation()
  const viewedChanges = useChatStore((s) => s.viewedChanges)
  const changeset = useChatStore((s) => s.changeset)

  // Check if all files associated with this message are viewed
  // For now, we consider it viewed if user has viewed any files
  // In the future, we can map files to specific messages
  const isViewed = viewedChanges.size > 0 && viewedChanges.size >= changeset.filter(f => !viewedChanges.has(f.path)).length + viewedChanges.size

  if (fileCount === 0) return null

  return (
    <div
      onClick={onClick}
      className={cn(
        "mt-2 inline-flex cursor-pointer items-center gap-2 rounded-lg",
        "border px-3 py-1.5 text-[11px] transition-all duration-200",
        isViewed
          ? "border-border/40 bg-muted/20 text-muted-foreground/60 hover:bg-muted/40"
          : "border-primary/20 bg-primary/5 text-primary hover:bg-primary/10 shadow-sm",
        className
      )}
    >
      <FileDiff
        className={cn(
          "h-3.5 w-3.5",
          isViewed ? "opacity-30" : "opacity-70"
        )}
      />
      <span
        className={cn(
          "font-semibold uppercase tracking-tight",
          isViewed ? "opacity-60" : "opacity-90"
        )}
      >
        {isViewed
          ? t("chat.changeset.viewed", "已巡检 {{count}} 个文件", { count: fileCount })
          : t("chat.changeset.newChanges", "本次修改了 {{count}} 个文件", { count: fileCount })}
      </span>
      {!isViewed && (
        <span className="flex items-center gap-1 font-bold ml-1">
          <span className="opacity-30">·</span>
          <span className="hover:underline">
            {t("chat.changeset.viewChanges", "点击审查")}
          </span>
          <ChevronRight className="h-3 w-3" />
        </span>
      )}
    </div>
  )
}
