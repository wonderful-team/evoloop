import { GitDiff, ChevronRight } from "lucide-react"
import { useTranslation } from "react-i18next"
import { cn } from "@evoloop/shared/lib/utils"

interface ChangesetInlineHintProps {
  fileCount: number
  isViewed?: boolean
  onClick?: () => void
  className?: string
}

export function ChangesetInlineHint({
  fileCount,
  isViewed = false,
  onClick,
  className,
}: ChangesetInlineHintProps) {
  const { t } = useTranslation()

  if (fileCount === 0) return null

  return (
    <div
      onClick={onClick}
      className={cn(
        "mt-2 inline-flex cursor-pointer items-center gap-2 rounded-lg",
        "border px-3 py-2 text-sm transition-colors",
        isViewed
          ? "border-muted bg-muted/30 text-muted-foreground hover:bg-muted/50"
          : "border-amber-200 bg-amber-50 hover:bg-amber-100 dark:border-amber-900 dark:bg-amber-950/30 dark:hover:bg-amber-900/30",
        className
      )}
    >
      <GitDiff
        className={cn(
          "h-4 w-4",
          isViewed ? "text-muted-foreground" : "text-amber-600 dark:text-amber-400"
        )}
      />
      <span
        className={cn(
          "font-medium",
          isViewed
            ? "text-muted-foreground"
            : "text-amber-800 dark:text-amber-200"
        )}
      >
        {isViewed
          ? t("chat.changeset.viewed", "已查看 {{count}} 个文件", { count: fileCount })
          : t("chat.changeset.newChanges", "本次修改了 {{count}} 个文件", { count: fileCount })}
      </span>
      {!isViewed && (
        <>
          <span className="text-amber-600 dark:text-amber-400">·</span>
          <span className="text-amber-600 hover:underline dark:text-amber-400">
            {t("chat.changeset.viewChanges", "查看变更")}
          </span>
          <ChevronRight className="h-3 w-3 text-amber-500" />
        </>
      )}
    </div>
  )
}
