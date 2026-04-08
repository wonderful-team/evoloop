import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import {
  ChevronDown,
  ChevronRight,
  FileCode,
  Folder,
  Loader2,
  Pin,
  Quote,
} from "lucide-react"
import { useState } from "react"
import { useTranslation } from "react-i18next"
import { toast } from "sonner"
import { FilesService, ResourcesService } from "@/client"
import { Button } from "@evoloop/shared/components/ui/button"
import {
  ContextMenu,
  ContextMenuContent,
  ContextMenuItem,
  ContextMenuTrigger,
} from "@evoloop/shared/components/ui/context-menu"
import { cn } from "@evoloop/shared/lib/utils"
import { isLoggedIn } from "@/hooks/useAuth"

interface FileNode {
  name: string
  path: string
  type: "file" | "directory"
}

interface FileTreeProps {
  projectId: number
  path?: string
  level?: number
  onSelectFile: (file: FileNode) => void
  onQuoteFile?: (file: FileNode) => void
}

export function FileTree({
  projectId,
  path = "",
  level = 0,
  onSelectFile,
  onQuoteFile,
}: FileTreeProps) {
  const { t } = useTranslation()
  const {
    data: files,
    isLoading,
    error,
  } = useQuery({
    queryKey: ["files", projectId, path],
    queryFn: () => FilesService.listFiles({ projectId, path }),
    staleTime: 1000 * 60 * 5, // Cache for 5 mins
    enabled: isLoggedIn(), // Only fetch if user is logged in
  })

  if (isLoading) {
    return (
      <div className="pl-4 py-1 text-xs text-muted-foreground flex items-center">
        <Loader2 className="h-3 w-3 animate-spin mr-1" /> {t("files.loading")}
      </div>
    )
  }

  if (error) {
    return (
      <div className="pl-4 py-1 text-xs text-destructive">
        {t("files.error")}
      </div>
    )
  }

  if (!files || (files as any).length === 0) {
    return (
      <div className="pl-4 py-1 text-xs text-muted-foreground italic">
        {t("files.empty")}
      </div>
    )
  }

  // Backend returns FileNode[] directly
  const fileList = files as unknown as FileNode[]

  return (
    <div className="text-sm">
      {fileList.map((node) => (
        <FileTreeNode
          key={node.path}
          node={node}
          level={level}
          projectId={projectId}
          onSelectFile={onSelectFile}
          onQuoteFile={onQuoteFile}
        />
      ))}
    </div>
  )
}

function FileTreeNode({
  node,
  level,
  projectId,
  onSelectFile,
  onQuoteFile,
}: {
  node: FileNode
  level: number
  projectId: number
  onSelectFile: (file: FileNode) => void
  onQuoteFile?: (file: FileNode) => void
}) {
  const [isOpen, setIsOpen] = useState(false)
  const isFolder = node.type === "directory"
  const { t } = useTranslation()
  const queryClient = useQueryClient()

  const pinResourceMutation = useMutation({
    mutationFn: async () => {
      return ResourcesService.createResource({
        projectId,
        requestBody: {
          type: "file",
          name: node.name,
          content: node.path,
        },
      })
    },
    onSuccess: () => {
      toast.success(t("files.pinnedSuccess", "File pinned"))
      queryClient.invalidateQueries({
        queryKey: ["projectResources", projectId],
      })
    },
    onError: () => toast.error(t("files.pinnedError", "Failed to pin file")),
  })

  const handleClick = (e: React.MouseEvent) => {
    e.stopPropagation()
    if (isFolder) {
      setIsOpen(!isOpen)
    } else {
      onSelectFile(node)
    }
  }

  const content = (
    <div
      className={cn(
        "flex items-center gap-1.5 py-1 px-2 hover:bg-accent/50 cursor-pointer rounded-sm select-none whitespace-nowrap transition-colors group",
      )}
      style={{ paddingLeft: `${level * 12 + 8}px` }}
      onClick={handleClick}
    >
      {isFolder ? (
        <span className="text-muted-foreground mr-0.5 shrink-0">
          {isOpen ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
        </span>
      ) : (
        <span className="w-4 shrink-0" /> // Spacer
      )}

      {isFolder ? (
        <Folder size={14} className="text-blue-400/80 shrink-0" />
      ) : (
        <FileCode size={14} className="text-muted-foreground shrink-0" />
      )}

      <span className="truncate flex-1">{node.name}</span>

      {!isFolder && (
        <Button
          variant="ghost"
          size="icon"
          className="h-5 w-5 opacity-0 group-hover:opacity-100 transition-opacity shrink-0 mr-1"
          title={t("files.pinToResources", "Pin to Resources")}
          onClick={(e) => {
            e.stopPropagation()
            pinResourceMutation.mutate()
          }}
          disabled={pinResourceMutation.isPending}
        >
          {pinResourceMutation.isPending ? (
            <Loader2 className="h-3 w-3 animate-spin" />
          ) : (
            <Pin
              size={12}
              className="text-muted-foreground hover:text-primary"
            />
          )}
        </Button>
      )}
    </div>
  )

  return (
    <div>
      {!isFolder && onQuoteFile ? (
        <ContextMenu>
          <ContextMenuTrigger asChild>{content}</ContextMenuTrigger>
          <ContextMenuContent>
            <ContextMenuItem onClick={() => onQuoteFile(node)}>
              <Quote size={14} className="mr-2" />
              {t("chat.interface.quoteFile", "Quote File")}
            </ContextMenuItem>
          </ContextMenuContent>
        </ContextMenu>
      ) : (
        content
      )}

      {isFolder && isOpen && (
        <div className="border-l ml-4 pl-1 border-muted/20">
          <FileTree
            projectId={projectId}
            path={node.path}
            level={level + 1}
            onSelectFile={onSelectFile}
            onQuoteFile={onQuoteFile}
          />
        </div>
      )}
    </div>
  )
}
