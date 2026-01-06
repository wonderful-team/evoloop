import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import {
  ChevronDown,
  ChevronRight,
  FileCode,
  Folder,
  Loader2,
  Pin,
} from "lucide-react"
import { useState } from "react"
import { useTranslation } from "react-i18next"
import { toast } from "sonner"
import { FilesService, ResourcesService } from "@/client"
import { Button } from "@/components/ui/button"
import { cn } from "@/lib/utils"

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
}

export function FileTree({
  projectId,
  path = "",
  level = 0,
  onSelectFile,
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
}: {
  node: FileNode
  level: number
  projectId: number
  onSelectFile: (file: FileNode) => void
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

  return (
    <div>
      <div
        className={cn(
          "flex items-center gap-1.5 py-1 px-2 hover:bg-accent/50 cursor-pointer rounded-sm select-none whitespace-nowrap transition-colors group",
          // Indentation handled by component nesting or padding?
          // Since we nest FileTree, we don't need manual level content padding if the container handles indentation.
          // BUT here we nest the OUTPUT of FileTree.
          // Let's use simple padding here.
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

      {isFolder && isOpen && (
        <div className="border-l ml-4 pl-1 border-muted/20">
          <FileTree
            projectId={projectId}
            path={node.path}
            level={level + 1}
            onSelectFile={onSelectFile}
          />
        </div>
      )}
    </div>
  )
}
