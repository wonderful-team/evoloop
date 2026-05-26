import { useQuery, useQueryClient } from "@tanstack/react-query"
import { Link } from "@tanstack/react-router"
import {
  ChevronDown,
  ChevronRight,
  FileCode,
  Folder,
  Loader2,
  Quote,
  Edit2,
  Trash2,
  FolderPlus,
  Eye,
} from "lucide-react"
import { useState } from "react"
import { useTranslation } from "react-i18next"
import { toast } from "sonner"
import { FilesService } from "@/client"
import { Button } from "@evoloop/shared/components/ui/button"
import { Input } from "@evoloop/shared/components/ui/input"
import {
  ContextMenu,
  ContextMenuContent,
  ContextMenuItem,
  ContextMenuTrigger,
  ContextMenuSeparator,
} from "@evoloop/shared/components/ui/context-menu"
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@evoloop/shared/components/ui/alert-dialog"
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
  isCreatingRootFolder?: boolean
  onCreateRootFolder?: (name: string) => Promise<void>
  onCancelCreateRootFolder?: () => void
}

export function FileTree({
  projectId,
  path = "",
  level = 0,
  onSelectFile,
  onQuoteFile,
  isCreatingRootFolder,
  onCreateRootFolder,
  onCancelCreateRootFolder,
}: FileTreeProps) {
  const { t } = useTranslation()
  const queryClient = useQueryClient()
  const [isDragOver, setIsDragOver] = useState(false)
  const [rootFolderInput, setRootFolderInput] = useState("")

  const {
    data: files,
    isLoading,
    error,
  } = useQuery({
    queryKey: ["files", projectId, path],
    queryFn: () => FilesService.listFiles({ projectId, path }),
    staleTime: 1000 * 60 * 5, // Cache for 5 mins
    enabled: isLoggedIn(), // Only fetch if user is logged in
    retry: (failureCount, error: any) => {
      if (error?.status === 404) return false;
      return failureCount < 3;
    },
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
        <Loader2 className="h-3 w-3 animate-spin mr-1" /> {t("files.loading", { defaultValue: "加载中..." })}
      </div>
    )
  }

  if (error) {
    const isGlobalNotConfigured = projectId === 0 && (error as any).status === 404;

    return (
      <div className="pl-4 py-2 text-xs text-destructive flex flex-col items-start gap-2">
        <span>{isGlobalNotConfigured ? t("files.workspaceNotConfigured", { defaultValue: "尚未配置全局工作区目录" }) : t("files.error", { defaultValue: "加载失败" })}</span>
        {isGlobalNotConfigured && (
          <Button variant="outline" size="sm" className="h-6 text-[10px]" asChild>
            <Link to="/settings">前往设置</Link>
          </Button>
        )}
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
        {level === 0 && isCreatingRootFolder && (
          <div className="flex items-center gap-1.5 py-1 px-2 rounded-sm whitespace-nowrap mb-2" style={{ paddingLeft: `${level * 12 + 8}px` }}>
            <span className="w-4 shrink-0" />
            <Folder size={14} className="text-blue-400/80 shrink-0" />
            <Input 
              autoFocus
              className="h-6 text-xs px-1.5 py-0 border-primary/50 focus-visible:ring-1 focus-visible:ring-offset-0 w-full max-w-[200px]"
              value={rootFolderInput}
              onChange={(e) => setRootFolderInput(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter" || e.key === "Escape") {
                  if (e.key === "Escape") setRootFolderInput("")
                  e.currentTarget.blur()
                }
              }}
              onBlur={async () => {
                if (rootFolderInput.trim() && onCreateRootFolder) {
                  await onCreateRootFolder(rootFolderInput.trim())
                } else if (onCancelCreateRootFolder) {
                  onCancelCreateRootFolder()
                }
                setRootFolderInput("")
              }}
            />
          </div>
        )}
        {t("files.empty", { defaultValue: "空文件夹" })} (Drop files here to upload)
      </div>
    )
  }

  // Backend returns FileNode[] directly
  const fileList = (files as unknown as FileNode[]).filter(node => 
    !(level === 0 && node.name === "PROJECT.md")
  )

  return (
    <div 
      className={cn("text-sm transition-colors rounded-md", isDragOver && level === 0 && "bg-primary/5 border-dashed border border-primary/30 min-h-[50px]")}
      onDragOver={level === 0 ? handleDragOver : undefined}
      onDragLeave={level === 0 ? handleDragLeave : undefined}
      onDrop={level === 0 ? handleDrop : undefined}
    >
      {level === 0 && isCreatingRootFolder && (
        <div className="flex items-center gap-1.5 py-1 px-2 rounded-sm whitespace-nowrap" style={{ paddingLeft: `${level * 12 + 8}px` }}>
          <span className="w-4 shrink-0" />
          <Folder size={14} className="text-blue-400/80 shrink-0" />
          <Input 
            autoFocus
            className="h-6 text-xs px-1.5 py-0 border-primary/50 focus-visible:ring-1 focus-visible:ring-offset-0 w-full max-w-[200px]"
            value={rootFolderInput}
            onChange={(e) => setRootFolderInput(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" || e.key === "Escape") {
                if (e.key === "Escape") setRootFolderInput("")
                e.currentTarget.blur()
              }
            }}
            onBlur={async () => {
              if (rootFolderInput.trim() && onCreateRootFolder) {
                await onCreateRootFolder(rootFolderInput.trim())
              } else if (onCancelCreateRootFolder) {
                onCancelCreateRootFolder()
              }
              setRootFolderInput("")
            }}
          />
        </div>
      )}
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
  const [isRenaming, setIsRenaming] = useState(false)
  const [renameInput, setRenameInput] = useState(node.name)
  const [isCreatingChild, setIsCreatingChild] = useState(false)
  const [childFolderInput, setChildFolderInput] = useState("")
  const [showDeleteConfirm, setShowDeleteConfirm] = useState(false)

  const isFolder = node.type === "directory"
  const { t } = useTranslation()
  const queryClient = useQueryClient()

  const refreshFiles = () => {
    queryClient.invalidateQueries({ queryKey: ["files", projectId] })
  }

  const handleClick = (e: React.MouseEvent) => {
    e.stopPropagation()
    if (isFolder) {
      setIsOpen(!isOpen)
    } else {
      onSelectFile(node)
    }
  }

  const handleDragStart = (e: React.DragEvent) => {
    e.stopPropagation()
    e.dataTransfer.setData("application/x-evoloop-file", node.path)
    e.dataTransfer.effectAllowed = "move"
  }

  const handleDragOver = (e: React.DragEvent) => {
    if (!isFolder) return
    e.preventDefault()
    e.stopPropagation()
    setIsDragOver(true)
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

    // Handle internal move
    const sourcePath = e.dataTransfer.getData("application/x-evoloop-file")
    if (sourcePath) {
      // Don't move into itself or its direct parent
      if (sourcePath !== node.path && sourcePath !== `${node.path}/${sourcePath.split('/').pop()}`) {
        try {
          await FilesService.moveFile({
            projectId,
            requestBody: {
              source_path: sourcePath,
              target_path: `${node.path}/${sourcePath.split('/').pop()}`
            }
          })
          refreshFiles()
          toast.success(t("files.moveSuccess", { defaultValue: "移动成功" }))
        } catch (error) {
          toast.error(t("files.moveError", { defaultValue: "移动失败" }))
        }
      }
      return
    }

    // Handle external upload
    if (e.dataTransfer.files && e.dataTransfer.files.length > 0) {
      await onUpload(node.path, e.dataTransfer.files)
    }
  }

  const handleRenameSubmit = async () => {
    setIsRenaming(false)
    const newName = renameInput.trim()
    if (!newName || newName === node.name) return
    const targetPath = node.path.substring(0, node.path.lastIndexOf('/')) + '/' + newName
    
    try {
      await FilesService.moveFile({
        projectId,
        requestBody: {
          source_path: node.path,
          target_path: targetPath.replace(/^\//, "") // ensure no leading slash if root
        }
      })
      refreshFiles()
    } catch (error) {
      toast.error(t("files.renameError", { defaultValue: "重命名失败" }))
      setRenameInput(node.name)
    }
  }

  const handleCreateChildSubmit = async () => {
    const newName = childFolderInput.trim()
    if (!newName) {
      setIsCreatingChild(false)
      return
    }
    try {
      await FilesService.createDirectory({
        projectId,
        requestBody: {
          path: `${node.path}/${newName}`
        }
      })
      setIsCreatingChild(false)
      setChildFolderInput("")
      refreshFiles()
      setIsOpen(true)
    } catch (error) {
      toast.error(t("files.createFolderError", { defaultValue: "创建文件夹失败" }))
    }
  }

  const handleDelete = async () => {
    setShowDeleteConfirm(false)
    try {
      await FilesService.deleteFile({
        projectId,
        path: node.path
      })
      refreshFiles()
    } catch (error) {
      toast.error(t("files.deleteError", { defaultValue: "删除失败" }))
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
      draggable
      onDragStart={handleDragStart}
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

      {isRenaming ? (
        <Input
          autoFocus
          className="h-5 text-xs px-1 py-0 border-primary/50 focus-visible:ring-1 focus-visible:ring-offset-0 w-full max-w-[200px]"
          value={renameInput}
          onChange={(e) => setRenameInput(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" || e.key === "Escape") {
              if (e.key === "Escape") {
                setIsRenaming(false)
                setRenameInput(node.name)
              }
              e.currentTarget.blur()
            }
          }}
          onBlur={handleRenameSubmit}
          onClick={(e) => e.stopPropagation()}
          onDoubleClick={(e) => e.stopPropagation()}
        />
      ) : (
        <span className="truncate flex-1">{node.name}</span>
      )}

      {!isFolder && onQuoteFile && !isRenaming && (
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
      <ContextMenu>
        <ContextMenuTrigger asChild>{content}</ContextMenuTrigger>
        <ContextMenuContent>
          {!isFolder && (
            <ContextMenuItem onClick={() => onSelectFile(node)}>
              <Eye size={14} className="mr-2" />
              {t("files.preview", { defaultValue: "预览" })}
            </ContextMenuItem>
          )}
          {!isFolder && onQuoteFile && (
            <ContextMenuItem onClick={() => onQuoteFile(node)}>
              <Quote size={14} className="mr-2" />
              {t("chat.interface.quoteFile")}
            </ContextMenuItem>
          )}
          {isFolder && (
            <ContextMenuItem onClick={() => {
              setIsOpen(true)
              setIsCreatingChild(true)
            }}>
              <FolderPlus size={14} className="mr-2" />
              {t("files.newFolder", { defaultValue: "新建文件夹" })}
            </ContextMenuItem>
          )}
          {(onQuoteFile || isFolder) && <ContextMenuSeparator />}
          <ContextMenuItem onClick={() => {
            setRenameInput(node.name)
            setIsRenaming(true)
          }}>
            <Edit2 size={14} className="mr-2" />
            {t("files.rename", { defaultValue: "重命名" })}
          </ContextMenuItem>
          <ContextMenuItem onClick={() => setShowDeleteConfirm(true)} className="text-destructive focus:text-destructive">
            <Trash2 size={14} className="mr-2" />
            {t("common.delete", { defaultValue: "删除" })}
          </ContextMenuItem>
        </ContextMenuContent>
      </ContextMenu>

      <AlertDialog open={showDeleteConfirm} onOpenChange={setShowDeleteConfirm}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>{t("common.deleteConfirmTitle", { defaultValue: "确认删除" })}</AlertDialogTitle>
            <AlertDialogDescription>
              {t("files.deleteConfirm", { defaultValue: `确定要删除 ${node.name} 吗？` })}
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>{t("common.cancel", { defaultValue: "取消" })}</AlertDialogCancel>
            <AlertDialogAction className="bg-destructive hover:bg-destructive/90 text-destructive-foreground" onClick={handleDelete}>
              {t("common.delete", { defaultValue: "删除" })}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>

      {isFolder && isOpen && (
        <div className="border-l ml-4 pl-1 border-muted/20">
          {isCreatingChild && (
            <div className="flex items-center gap-1.5 py-1 px-2 rounded-sm whitespace-nowrap" style={{ paddingLeft: `${(level + 1) * 12 + 8}px` }}>
              <span className="w-4 shrink-0" />
              <Folder size={14} className="text-blue-400/80 shrink-0" />
              <Input 
                autoFocus
                className="h-6 text-xs px-1.5 py-0 border-primary/50 focus-visible:ring-1 focus-visible:ring-offset-0 w-full max-w-[200px]"
                value={childFolderInput}
                onChange={(e) => setChildFolderInput(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === "Enter" || e.key === "Escape") {
                    if (e.key === "Escape") {
                      setIsCreatingChild(false)
                      setChildFolderInput("")
                    }
                    e.currentTarget.blur()
                  }
                }}
                onBlur={handleCreateChildSubmit}
              />
            </div>
          )}
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
