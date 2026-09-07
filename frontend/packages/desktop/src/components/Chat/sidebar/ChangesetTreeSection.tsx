import { cn } from "@evoloop/shared/lib/utils"
import { useQuery } from "@tanstack/react-query"
import { FileCode } from "lucide-react"
import { useEffect } from "react"
import { useTranslation } from "react-i18next"
import { OpenAPI } from "@/client"
import { useChangesetStore } from "@/stores/changesetStore"

export interface ChangesetNode {
  name: string
  path: string
  is_dir: boolean
  operation?: "ADD" | "EDIT" | "DELETE"
  diff?: string
  children: ChangesetNode[]
}

interface ChangesetTreeSectionProps {
  activeThreadId?: string
  onSelectFile: (path: string, diff: string) => void
  defaultExpanded?: boolean
}

export function ChangesetTreeSection({
  activeThreadId,
  onSelectFile,
  defaultExpanded: _defaultExpanded = false,
}: ChangesetTreeSectionProps) {
  const { t } = useTranslation()
  const setChangeset = useChangesetStore((s) => s.setChangeset)
  const markChangeAsViewed = useChangesetStore((s) => s.markChangeAsViewed)
  const viewedChanges = useChangesetStore((s) => s.viewedChanges)

  const {
    data: changeset,
    isLoading,
    refetch,
  } = useQuery<ChangesetNode[]>({
    queryKey: ["threadChangeset", activeThreadId],
    queryFn: async () => {
      if (!activeThreadId) return []
      const res = await fetch(
        `${OpenAPI.BASE}/api/v1/conversations/${activeThreadId}/changeset`,
      )
      if (!res.ok) throw new Error(t("chat.changeset.fetchFailed"))
      return res.json()
    },
    enabled: !!activeThreadId,
  })

  useEffect(() => {
    const handleChangesetUpdate = (e: CustomEvent) => {
      if (e.detail?.threadId === activeThreadId) {
        refetch()
      }
    }
    window.addEventListener(
      "chat-changeset-updated",
      handleChangesetUpdate as EventListener,
    )
    return () =>
      window.removeEventListener(
        "chat-changeset-updated",
        handleChangesetUpdate as EventListener,
      )
  }, [activeThreadId, refetch])

  // Sync changeset to chatStore for badge count
  useEffect(() => {
    if (changeset) {
      const flatFiles: Array<{
        path: string
        operation: "ADD" | "EDIT" | "DELETE"
        diff?: string
        timestamp: string
      }> = []

      const extractFiles = (nodes: ChangesetNode[]) => {
        nodes.forEach((node) => {
          if (node.is_dir && node.children) {
            extractFiles(node.children)
          } else if (!node.is_dir && node.operation) {
            flatFiles.push({
              path: node.path,
              operation: node.operation,
              diff: node.diff,
              timestamp: new Date().toISOString(),
            })
          }
        })
      }

      extractFiles(changeset)
      setChangeset(flatFiles, activeThreadId)
    }
  }, [changeset, setChangeset, activeThreadId])

  // Convert to flat list
  const flatFiles: Array<{
    path: string
    operation: "ADD" | "EDIT" | "DELETE"
    diff?: string
  }> = []

  const extractFiles = (nodes: ChangesetNode[]) => {
    nodes.forEach((node) => {
      if (node.is_dir && node.children) {
        extractFiles(node.children)
      } else if (!node.is_dir && node.operation) {
        flatFiles.push({
          path: node.path,
          operation: node.operation,
          diff: node.diff,
        })
      }
    })
  }

  if (changeset) {
    extractFiles(changeset)
  }

  if (!flatFiles.length) {
    if (isLoading)
      return (
        <div className="p-4 text-center text-xs text-muted-foreground">
          {t("common.loading")}
        </div>
      )
    return null
  }

  return (
    <div className="p-1 space-y-1">
      {flatFiles.map((file) => {
        const isViewed = viewedChanges.has(file.path)
        const fileName = file.path.split("/").pop() || file.path
        const dirPath = file.path.substring(0, file.path.lastIndexOf("/"))

        return (
          <div
            key={file.path}
            className={cn(
              "flex items-center py-2 px-3 cursor-pointer hover:bg-primary/5 rounded-lg text-xs transition-all group/node relative",
              isViewed && "opacity-60",
            )}
            onClick={() => {
              onSelectFile(file.path, file.diff || "")
              markChangeAsViewed(file.path, activeThreadId)
            }}
          >
            {/* Activity Indicator */}
            {!isViewed && (
              <div className="absolute left-1 top-1/2 -translate-y-1/2 w-1 h-4 bg-primary rounded-full" />
            )}

            <FileCode
              className={cn(
                "h-4 w-4 mr-2 shrink-0",
                isViewed ? "text-muted-foreground" : "text-primary/70",
              )}
            />

            <div className="flex-1 min-w-0 mr-2 flex flex-col">
              <span
                className={cn(
                  "truncate font-medium tracking-tight",
                  isViewed && "text-muted-foreground",
                )}
              >
                {fileName}
              </span>
              {dirPath && (
                <span className="truncate font-mono text-[10px] text-muted-foreground/60">
                  {dirPath}
                </span>
              )}
            </div>

            <div className="flex items-center gap-1.5 shrink-0">
              {file.operation === "ADD" && (
                <span className="px-1.5 py-0.5 rounded-[4px] bg-success/10 text-success font-mono text-[9px] font-medium uppercase tracking-[0.08em] border border-success/20">
                  {t("chat.changeset.opAdd")}
                </span>
              )}
              {file.operation === "EDIT" && (
                <span className="px-1.5 py-0.5 rounded-[4px] bg-warning/10 text-warning font-mono text-[9px] font-medium uppercase tracking-[0.08em] border border-warning/20">
                  {t("chat.changeset.opMod")}
                </span>
              )}
              {file.operation === "DELETE" && (
                <span className="px-1.5 py-0.5 rounded-[4px] bg-destructive/10 text-destructive font-mono text-[9px] font-medium uppercase tracking-[0.08em] border border-destructive/20">
                  {t("chat.changeset.opDel")}
                </span>
              )}
            </div>
          </div>
        )
      })}
    </div>
  )
}
