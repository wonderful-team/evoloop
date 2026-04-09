import { useQuery } from "@tanstack/react-query"
import { useTranslation } from "react-i18next"
import { OpenAPI } from "@/client"
import {
    FileCode,
    Folder,
    ChevronRight,
    ChevronDown,
    PlusSquare,
    Edit,
    Trash2,
    Check,
} from "lucide-react"
import { useState, useEffect } from "react"
import { cn } from "@evoloop/shared/lib/utils"
import { useChatStore } from "@/stores/chatStore"

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

export function ChangesetTreeSection({ activeThreadId, onSelectFile, defaultExpanded = false }: ChangesetTreeSectionProps) {
    const { t } = useTranslation()
    const setChangeset = useChatStore((s) => s.setChangeset)
    const markChangeAsViewed = useChatStore((s) => s.markChangeAsViewed)
    const viewedChanges = useChatStore((s) => s.viewedChanges)

    const { data: changeset, isLoading } = useQuery<ChangesetNode[]>({
        queryKey: ["threadChangeset", activeThreadId],
        queryFn: async () => {
            if (!activeThreadId) return []
            const token = typeof OpenAPI.TOKEN === 'function' ? await (OpenAPI.TOKEN as any)() : OpenAPI.TOKEN;
            const res = await fetch(`${OpenAPI.BASE}/api/v1/conversations/${activeThreadId}/changeset`, {
                headers: {
                    ...(token ? { Authorization: `Bearer ${token}` } : {}),
                }
            })
            if (!res.ok) throw new Error("Failed to fetch changeset")
            return res.json()
        },
        enabled: !!activeThreadId,
        refetchInterval: 5000,
    })

    // Sync changeset to chatStore for badge count
    useEffect(() => {
        if (changeset) {
            const flatFiles: Array<{path: string; operation: 'ADD' | 'EDIT' | 'DELETE'; diff?: string; timestamp: string}> = []
            
            const extractFiles = (nodes: ChangesetNode[]) => {
                nodes.forEach(node => {
                    if (node.is_dir && node.children) {
                        extractFiles(node.children)
                    } else if (!node.is_dir && node.operation) {
                        flatFiles.push({
                            path: node.path,
                            operation: node.operation,
                            diff: node.diff,
                            timestamp: new Date().toISOString()
                        })
                    }
                })
            }
            
            extractFiles(changeset)
            setChangeset(flatFiles)
        }
    }, [changeset, setChangeset])

    // Recursive component for the tree
    const TreeNode = ({ node, level = 0 }: { node: ChangesetNode; level?: number }) => {
        const [isOpen, setIsOpen] = useState(defaultExpanded)
        const isViewed = viewedChanges.has(node.path)

        const handleToggle = (e: React.MouseEvent) => {
            e.stopPropagation()
            setIsOpen(!isOpen)
        }

        const handleSelect = () => {
            if (!node.is_dir) {
                onSelectFile(node.path, node.diff || "")
                // Mark as viewed when clicked
                markChangeAsViewed(node.path)
            } else {
                setIsOpen(!isOpen)
            }
        }

        return (
            <div className="select-none">
                <div
                    className={cn(
                        "flex items-center py-1.5 px-2 cursor-pointer hover:bg-muted/50 rounded-sm text-xs transition-colors group",
                        isViewed && !node.is_dir && "text-muted-foreground"
                    )}
                    style={{ paddingLeft: `${level * 12 + 8}px` }}
                    onClick={handleSelect}
                >
                    {node.is_dir ? (
                        <span onClick={handleToggle} className="p-0.5 hover:bg-background rounded mr-1">
                            {isOpen ? <ChevronDown className="h-3 w-3" /> : <ChevronRight className="h-3 w-3" />}
                        </span>
                    ) : (
                        <div className="w-4 mr-1" />
                    )}

                    {node.is_dir ? (
                        <Folder className="h-3.5 w-3.5 mr-1.5 text-blue-400" />
                    ) : (
                        <FileCode className={cn("h-3.5 w-3.5 mr-1.5", isViewed ? "text-muted-foreground" : "text-muted-foreground")} />
                    )}

                    <span className={cn("truncate flex-1", isViewed && !node.is_dir && "line-through opacity-60")}>{node.name}</span>

                    {!node.is_dir && (
                        <span className="ml-2 flex items-center gap-1">
                            {node.operation === "ADD" && !isViewed && <PlusSquare className="h-3 w-3 text-green-500" />}
                            {node.operation === "EDIT" && !isViewed && <Edit className="h-3 w-3 text-amber-500" />}
                            {node.operation === "DELETE" && !isViewed && <Trash2 className="h-3 w-3 text-red-500" />}
                            {isViewed && <Check className="h-3 w-3 text-muted-foreground" />}
                        </span>
                    )}
                </div>

                {node.is_dir && isOpen && (
                    <div className="mt-0.5">
                        {node.children.map((child) => (
                            <TreeNode key={child.path} node={child} level={level + 1} />
                        ))}
                    </div>
                )}
            </div>
        )
    }

    if (!changeset || changeset.length === 0) {
        if (isLoading) return <div className="p-4 text-center text-xs text-muted-foreground">{t("common.loading")}</div>
        return null
    }

    return (
        <div className="p-1">
            {changeset.map((node) => (
                <TreeNode key={node.path} node={node} />
            ))}
        </div>
    )
}
