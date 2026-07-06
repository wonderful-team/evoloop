import { cn } from "@evoloop/shared/lib/utils"
import { ChevronRight, FileDiff } from "lucide-react"
import { useTranslation } from "react-i18next"
import { useChangesetStore } from "@/stores/changesetStore"

interface ChangesetInlineHintProps {
  fileCount: number
  messageId?: string | number // Message ID to check viewed status
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
  const viewedChanges = useChangesetStore((s) => s.viewedChanges)
  const changeset = useChangesetStore((s) => s.changeset)

  // Check if all files associated with this message are viewed
  // For now, we consider it viewed if user has viewed any files
  // In the future, we can map files to specific messages
  const isViewed =
    viewedChanges.size > 0 &&
    viewedChanges.size >=
      changeset.filter((f) => !viewedChanges.has(f.path)).length +
        viewedChanges.size

  if (fileCount === 0) return null

  return (
    <div
      onClick={onClick}
      className={cn(
        "mt-4 inline-flex cursor-pointer items-center gap-2 py-1 transition-all duration-300 group/changeset",
        isViewed
          ? "text-muted-foreground/40"
          : "text-primary hover:text-primary/80",
        className,
      )}
    >
      <div
        className={cn(
          "p-1.5 rounded-md transition-colors",
          isViewed
            ? "bg-muted/10 group-hover/changeset:bg-muted/20"
            : "bg-primary/5 group-hover/changeset:bg-primary/10",
        )}
      >
        <FileDiff className="h-3.5 w-3.5" />
      </div>

      <div className="flex flex-col">
        <span className="text-[10px] font-bold uppercase tracking-[0.2em] opacity-50">
          {isViewed
            ? t("chat.changeset.viewed")
            : t("chat.changeset.fileChangeset")}
        </span>
        <span className="text-xs font-semibold">
          {isViewed
            ? t("chat.changeset.viewed", { count: fileCount })
            : t("chat.changeset.newChanges", { count: fileCount })}
          {!isViewed && (
            <span className="ml-2 inline-flex items-center gap-0.5 opacity-60 group-hover/changeset:opacity-100 transition-opacity">
              <span className="hover:underline">
                {t("chat.changeset.viewChanges")}
              </span>
              <ChevronRight className="h-3 w-3" />
            </span>
          )}
        </span>
      </div>
    </div>
  )
}
