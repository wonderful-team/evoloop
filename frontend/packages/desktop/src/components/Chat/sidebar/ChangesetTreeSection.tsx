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
} from "lucide-react"
import { useState } from "react"
import { cn } from "@evoloop/shared/lib/utils"

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
}

export function ChangesetTreeSection({ activeThreadId, onSelectFile }: ChangesetTreeSectionProps) {
    const { t } = useTranslation()

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

    // Recursive component for the tree
    const TreeNode = ({ node, level = 0 }: { node: ChangesetNode; level?: number }) => {
        const [isOpen, setIsOpen] = useState(true)

        const handleToggle = (e: React.MouseEvent) => {
            e.stopPropagation()
            setIsOpen(!isOpen)
        }

        const handleSelect = () => {
            if (!node.is_dir) {
                onSelectFile(node.path, node.diff || "")
            } else {
                setIsOpen(!isOpen)
            }
        }

        return (
            <div className="select-none">
                <div
                    className={cn(
                        "flex items-center py-1.5 px-2 cursor-pointer hover:bg-muted/50 rounded-sm text-xs transition-colors group"
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
                        <FileCode className="h-3.5 w-3.5 mr-1.5 text-muted-foreground" />
                    )}

                    <span className="truncate flex-1">{node.name}</span>

                    {!node.is_dir && node.operation && (
                        <span className="ml-2">
                            {node.operation === "ADD" && <PlusSquare className="h-3 w-3 text-green-500" />}
                            {node.operation === "EDIT" && <Edit className="h-3 w-3 text-amber-500" />}
                            {node.operation === "DELETE" && <Trash2 className="h-3 w-3 text-red-500" />}
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
        if (isLoading) return <div className="p-4 text-center text-xs text-muted-foreground">{t("common.loading", "Loading...")}</div>
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
