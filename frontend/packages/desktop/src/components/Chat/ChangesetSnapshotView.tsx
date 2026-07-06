import { Badge } from "@evoloop/shared/components/ui/badge"
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "@evoloop/shared/components/ui/tooltip"
import { cn } from "@evoloop/shared/lib/utils"
import { ChevronRight, Edit2, FileCode2, Minus, Plus } from "lucide-react"
import { memo } from "react"
import { useTranslation } from "react-i18next"

interface ChangesetFile {
  path: string
  operation: "added" | "modified" | "deleted" | "renamed"
  diff?: string
}

interface ChangesetSnapshotProps {
  files: ChangesetFile[]
  totalCount: number
  onViewDetails?: (path: string, diff?: string) => void
}

/**
 * Concise horizontal changeset snapshot.
 * Inspired by IDE-style file chips.
 */
export const ChangesetSnapshot = memo(
  ({ files, totalCount, onViewDetails }: ChangesetSnapshotProps) => {
    const { t } = useTranslation()

    if (files.length === 0) return null

    // Helper to get file name from path
    const getFileName = (path: string) => {
      const parts = path.split("/")
      return parts[parts.length - 1]
    }

    // Helper to get operation icon/color
    const getOpStyles = (op: ChangesetFile["operation"]) => {
      switch (op) {
        case "added":
          return {
            color: "text-green-500",
            bg: "bg-green-500/10",
            icon: <Plus className="h-2.5 w-2.5" />,
          }
        case "deleted":
          return {
            color: "text-red-500",
            bg: "bg-red-500/10",
            icon: <Minus className="h-2.5 w-2.5" />,
          }
        default:
          return {
            color: "text-blue-500",
            bg: "bg-blue-500/10",
            icon: <Edit2 className="h-2.5 w-2.5" />,
          }
      }
    }

    return (
      <div className="flex flex-col gap-2 py-2 mt-2 select-none group/changeset">
        {/* Header */}
        <div className="flex items-center gap-2 px-1">
          <span className="text-[11px] font-semibold uppercase tracking-wider text-muted-foreground/70">
            {t("chat.sidebar.agentChanges")}
          </span>
          <Badge
            variant="secondary"
            className="h-4 px-1.5 text-[10px] font-medium bg-muted/30 text-muted-foreground border-none"
          >
            {totalCount}
          </Badge>
        </div>

        {/* Horizontal Scrollable Area */}
        <div className="relative">
          <div className="flex items-center gap-2 overflow-x-auto pb-1 no-scrollbar scroll-smooth mask-fade-right">
            <TooltipProvider delayDuration={300}>
              {files.map((file, idx) => {
                const styles = getOpStyles(file.operation)
                return (
                  <Tooltip key={`${file.path}-${idx}`}>
                    <TooltipTrigger asChild>
                      <button
                        onClick={() => onViewDetails?.(file.path, file.diff)}
                        className={cn(
                          "flex items-center gap-2 px-2 py-1 rounded-md border border-border/40",
                          "bg-muted/10 hover:bg-muted/20 hover:border-border/80 transition-all shrink-0",
                          "active:scale-95",
                        )}
                      >
                        <FileCode2 className="h-3.5 w-3.5 text-muted-foreground/70" />
                        <span className="text-xs font-medium max-w-[150px] truncate">
                          {getFileName(file.path)}
                        </span>
                        <div
                          className={cn(
                            "flex items-center gap-0.5",
                            styles.color,
                          )}
                        >
                          {styles.icon}
                          <span className="text-[10px] opacity-80">
                            {file.operation === "added"
                              ? "+1"
                              : file.operation === "deleted"
                                ? "-1"
                                : "±1"}
                          </span>
                        </div>
                      </button>
                    </TooltipTrigger>
                    <TooltipContent
                      side="bottom"
                      className="text-[10px] py-1 px-2"
                    >
                      {getFileName(file.path)}
                    </TooltipContent>
                  </Tooltip>
                )
              })}
            </TooltipProvider>

            {/* View All Pill */}
            {totalCount > files.length && (
              <button
                onClick={() => onViewDetails?.("")}
                className="flex items-center gap-1 px-2 py-1 rounded-md border border-dashed border-border/60 
                         text-muted-foreground hover:text-foreground hover:border-border transition-colors shrink-0"
              >
                <span className="text-[11px] font-medium">
                  {t("chat.changeset.more", {
                    count: totalCount - files.length,
                  })}
                </span>
                <ChevronRight className="h-3 w-3" />
              </button>
            )}
          </div>
        </div>
      </div>
    )
  },
)

ChangesetSnapshot.displayName = "ChangesetSnapshot"
