import { Folder, FileCode, ChevronRight, ChevronDown, Loader2 } from "lucide-react"
import { useState } from "react"
import { useQuery } from "@tanstack/react-query"
import { cn } from "@/lib/utils"
import { FilesService } from "@/client"

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

export function FileTree({ projectId, path = "", level = 0, onSelectFile }: FileTreeProps) {
    const { data: files, isLoading, error } = useQuery({
        queryKey: ["files", projectId, path],
        queryFn: () => FilesService.listFiles({ projectId, path }),
        staleTime: 1000 * 60 * 5, // Cache for 5 mins
    })

    if (isLoading) {
        return <div className="pl-4 py-1 text-xs text-muted-foreground flex items-center"><Loader2 className="h-3 w-3 animate-spin mr-1" /> Loading...</div>
    }

    if (error) {
        return <div className="pl-4 py-1 text-xs text-destructive">Error loading</div>
    }

    if (!files || (files as any).length === 0) {
        return <div className="pl-4 py-1 text-xs text-muted-foreground italic">Empty</div>
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

function FileTreeNode({ node, level, projectId, onSelectFile }: { node: FileNode, level: number, projectId: number, onSelectFile: (file: FileNode) => void }) {
    const [isOpen, setIsOpen] = useState(false)
    const isFolder = node.type === "directory"

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
                    "flex items-center gap-1.5 py-1 px-2 hover:bg-accent/50 cursor-pointer rounded-sm select-none whitespace-nowrap transition-colors",
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

                <span className="truncate">{node.name}</span>
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
