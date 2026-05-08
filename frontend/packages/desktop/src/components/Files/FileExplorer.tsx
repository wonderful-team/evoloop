import { useQuery } from "@tanstack/react-query"
import { FileCode, Folder, FolderOpen, Loader2 } from "lucide-react"
import { useState } from "react"
import { useTranslation } from "react-i18next"
import { FilesService } from "@/client"

// Types matching backend
interface FileNode {
  name: string
  path: string
  type: "file" | "directory"
  children?: FileNode[]
}

interface FileExplorerProps {
  projectId: number
}

export function FileExplorer({ projectId }: FileExplorerProps) {
  const { t } = useTranslation()
  const [selectedPath, setSelectedPath] = useState<string | null>(null)

  return (
    <div className="flex h-full border rounded-lg bg-background overflow-hidden">
      <div className="w-1/4 min-w-[250px] border-r bg-muted/30 flex flex-col">
        <div className="p-3 border-b font-medium text-sm text-muted-foreground">
          {t("files.title")}
        </div>
        <div className="flex-1 overflow-auto p-2">
          <FileTree
            projectId={projectId}
            onSelect={setSelectedPath}
            selectedPath={selectedPath}
          />
        </div>
      </div>
      <div className="flex-1 flex flex-col bg-card">
        {selectedPath ? (
          <FileContentV projectId={projectId} path={selectedPath} />
        ) : (
          <div className="flex-1 flex items-center justify-center text-muted-foreground">
            {t("files.selectPrompt")}
          </div>
        )}
      </div>
    </div>
  )
}

function FileTree({
  projectId,
  onSelect,
  selectedPath,
}: {
  projectId: number
  onSelect: (p: string) => void
  selectedPath: string | null
}) {
  const { t } = useTranslation()
  const {
    data: files,
    isLoading,
    error,
  } = useQuery({
    queryKey: ["files", projectId, "root"],
    queryFn: () => FilesService.listFiles({ projectId }),
  })

  if (isLoading)
    return (
      <div className="p-4 text-sm text-muted-foreground">
        <Loader2 className="w-4 h-4 animate-spin" />
      </div>
    )
  if (error)
    return (
      <div className="p-4 text-sm text-destructive">{t("files.error")}</div>
    )

  return (
    <div className="space-y-1">
      {files?.map((node: any) => (
        <FileTreeNode
          key={node.path}
          node={node}
          projectId={projectId}
          onSelect={onSelect}
          selectedPath={selectedPath}
          level={0}
        />
      ))}
    </div>
  )
}

function FileTreeNode({
  node,
  projectId,
  onSelect,
  selectedPath,
  level,
}: {
  node: FileNode
  projectId: number
  onSelect: (p: string) => void
  selectedPath: string | null
  level: number
}) {
  const { t } = useTranslation()
  const [isOpen, setIsOpen] = useState(false)
  const isFolder = node.type === "directory"

  // Lazy load children
  const { data: children, isLoading } = useQuery({
    queryKey: ["files", projectId, node.path],
    queryFn: () => FilesService.listFiles({ projectId, path: node.path }),
    enabled: isFolder && isOpen, // Only fetch when expanded
    staleTime: 60 * 1000,
  })

  const handleClick = () => {
    if (isFolder) {
      setIsOpen(!isOpen)
    } else {
      onSelect(node.path)
    }
  }

  const isSelected = selectedPath === node.path

  return (
    <div>
      <div
        className={`flex items-center gap-1.5 py-1 px-2 rounded-md cursor-pointer text-sm select-none transition-colors ${isSelected ? "bg-primary/10 text-primary font-medium" : "hover:bg-muted"}`}
        style={{ paddingLeft: `${level * 12 + 8}px` }}
        onClick={handleClick}
      >
        {isFolder ? (
          isOpen ? (
            <FolderOpen size={14} className="text-blue-500 shrink-0" />
          ) : (
            <Folder size={14} className="text-slate-400 shrink-0" />
          )
        ) : (
          <FileCode size={14} className="text-slate-500 shrink-0" />
        )}
        <span className="truncate">{node.name}</span>
      </div>

      {isFolder && isOpen && (
        <div>
          {isLoading ? (
            <div className="pl-6 py-1 text-xs text-muted-foreground flex items-center gap-2">
              <Loader2 size={10} className="animate-spin" /> {t("files.loading")}
            </div>
          ) : (
            children?.map((child: any) => (
              <FileTreeNode
                key={child.path}
                node={child}
                projectId={projectId}
                onSelect={onSelect}
                selectedPath={selectedPath}
                level={level + 1}
              />
            ))
          )}
        </div>
      )}
    </div>
  )
}

function FileContentV({
  projectId,
  path,
}: {
  projectId: number
  path: string
}) {
  const { t } = useTranslation()
  const { data: content, isLoading } = useQuery({
    queryKey: ["fileContent", projectId, path],
    queryFn: () => FilesService.getFileContent({ projectId, path }),
  })

  if (isLoading)
    return (
      <div className="flex-1 flex items-center justify-center text-muted-foreground">
        <Loader2 className="w-6 h-6 animate-spin" />
      </div>
    )

  // Cast to any because TS might not know content field from generic response yet?
  // Actually generated SDK should have typed it as FileContent return.
  // But let's be safe.
  const fileData = content as any

  return (
    <div className="flex flex-col h-full overflow-hidden">
      <div className="border-b px-4 py-2 text-sm font-medium bg-muted/10 flex items-center justify-between">
        <span className="text-muted-foreground">{path}</span>
        <span className="text-xs uppercase text-slate-400">
          {fileData?.language || t("files.text")}
        </span>
      </div>
      <div className="flex-1 overflow-auto p-4 bg-[#1e1e1e] text-slate-200 font-mono text-sm leading-relaxed">
        <pre>{fileData?.content}</pre>
      </div>
    </div>
  )
}
