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
import { useState, useCallback } from "react"
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
  const queryClient = useQueryClient()
  const [isDragOver, setIsDragOver] = useState(false)

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

  const handleUpload = async (targetPath: string, files: FileList, overwrite = false) => {
    for (let i = 0; i < files.length; i++) {
      const file = files[i]
      try {
        await FilesService.workspaceUpload({
          projectId,
          formData: {
            file: file as any,
            target_dir: targetPath,
            overwrite: overwrite as any,
          }
        })
      } catch (error: any) {
        if (error.status === 409 || error.body?.detail?.includes("already exists")) {
          if (window.confirm(t("files.overwritePrompt", { defaultValue: `文件 ${file.name} 已存在，是否覆盖？` }))) {
            const dt = new DataTransfer()
            dt.items.add(file)
            await handleUpload(targetPath, dt.files, true)
          }
        } else {
          toast.error(t("files.uploadError", { defaultValue: `上传 ${file.name} 失败` }))
        }
      }
    }
    queryClient.invalidateQueries({ queryKey: ["files", projectId] })
  }

  const handleDragOver = (e: React.DragEvent) => {
    e.preventDefault()
    e.stopPropagation()
    setIsDragOver(true)
  }

  const handleDragLeave = (e: React.DragEvent) => {
    e.preventDefault()
    e.stopPropagation()
    setIsDragOver(false)
  }

  const handleDrop = async (e: React.DragEvent) => {
    e.preventDefault()
    e.stopPropagation()
    setIsDragOver(false)
    if (e.dataTransfer.files && e.dataTransfer.files.length > 0) {
      await handleUpload(path, e.dataTransfer.files)
    }
  }

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
      <div 
        className={cn("pl-4 py-4 text-xs text-muted-foreground italic rounded-md transition-colors", isDragOver && "bg-primary/10 border-dashed border border-primary/50")}
        onDragOver={handleDragOver}
        onDragLeave={handleDragLeave}
        onDrop={handleDrop}
      >
        {t("files.empty")} (Drop files here to upload)
      </div>
    )
  }

  // Backend returns FileNode[] directly
  const fileList = files as unknown as FileNode[]

  return (
    <div 
      className={cn("text-sm transition-colors rounded-md", isDragOver && level === 0 && "bg-primary/5 border-dashed border border-primary/30 min-h-[50px]")}
      onDragOver={level === 0 ? handleDragOver : undefined}
      onDragLeave={level === 0 ? handleDragLeave : undefined}
      onDrop={level === 0 ? handleDrop : undefined}
    >
      {fileList.map((node) => (
        <FileTreeNode
          key={node.path}
          node={node}
          level={level}
          projectId={projectId}
          onSelectFile={onSelectFile}
          onQuoteFile={onQuoteFile}
          onUpload={handleUpload}
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
  onUpload,
}: {
  node: FileNode
  level: number
  projectId: number
  onSelectFile: (file: FileNode) => void
  onQuoteFile?: (file: FileNode) => void
  onUpload: (targetPath: string, files: FileList) => Promise<void>
}) {
  const [isOpen, setIsOpen] = useState(false)
  const [isDragOver, setIsDragOver] = useState(false)
  const isFolder = node.type === "directory"
  const { t } = useTranslation()

  const handleClick = (e: React.MouseEvent) => {
    e.stopPropagation()
    if (isFolder) {
      setIsOpen(!isOpen)
    } else {
      onSelectFile(node)
    }
  }

  const handleDragOver = (e: React.DragEvent) => {
    if (!isFolder) return
    e.preventDefault()
    e.stopPropagation()
    setIsDragOver(true)
    if (!isOpen) {
      // Optional: auto-open folder after a short delay
    }
  }

  const handleDragLeave = (e: React.DragEvent) => {
    if (!isFolder) return
    e.preventDefault()
    e.stopPropagation()
    setIsDragOver(false)
  }

  const handleDrop = async (e: React.DragEvent) => {
    if (!isFolder) return
    e.preventDefault()
    e.stopPropagation()
    setIsDragOver(false)
    if (e.dataTransfer.files && e.dataTransfer.files.length > 0) {
      await onUpload(node.path, e.dataTransfer.files)
    }
  }

  const content = (
    <div
      className={cn(
        "flex items-center gap-1.5 py-1 px-2 hover:bg-accent/50 cursor-pointer rounded-sm select-none whitespace-nowrap transition-colors group",
        isDragOver && isFolder && "bg-primary/20 ring-1 ring-primary"
      )}
      style={{ paddingLeft: `${level * 12 + 8}px` }}
      onClick={handleClick}
      onDragOver={handleDragOver}
      onDragLeave={handleDragLeave}
      onDrop={handleDrop}
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

      {!isFolder && onQuoteFile && (
        <Button
          variant="ghost"
          size="icon"
          className="h-5 w-5 opacity-0 group-hover:opacity-100 transition-opacity shrink-0 mr-1"
          title={t("chat.interface.quoteFile")}
          onClick={(e) => {
            e.stopPropagation()
            onQuoteFile(node)
          }}
        >
          <Quote
            size={12}
            className="text-muted-foreground hover:text-primary"
          />
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
              {t("chat.interface.quoteFile")}
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
