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
            // Cookie Session is sent automatically by fetch.
            const res = await fetch(`${OpenAPI.BASE}/api/v1/conversations/${activeThreadId}/changeset`)
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
                        "flex items-center py-2 px-3 cursor-pointer hover:bg-primary/5 rounded-lg text-xs transition-all group/node relative",
                        isViewed && !node.is_dir && "opacity-60"
                    )}
                    style={{ paddingLeft: `${level * 16 + 12}px` }}
                    onClick={handleSelect}
                >
                    {/* Activity Indicator (for unviewed) */}
                    {!node.is_dir && !isViewed && (
                        <div className="absolute left-1 top-1/2 -translate-y-1/2 w-1 h-4 bg-primary rounded-full" />
                    )}

                    {node.is_dir ? (
                        <span onClick={handleToggle} className="p-0.5 hover:bg-background rounded mr-1.5 transition-transform group-hover/node:scale-110">
                            {isOpen ? <ChevronDown className="h-3 w-3 opacity-40" /> : <ChevronRight className="h-3 w-3 opacity-40" />}
                        </span>
                    ) : (
                        <div className="w-4 mr-1.5" />
                    )}

                    {node.is_dir ? (
                        <Folder className="h-4 w-4 mr-2 text-primary/60" />
                    ) : (
                        <FileCode className={cn("h-4 w-4 mr-2", isViewed ? "text-muted-foreground" : "text-primary/70")} />
                    )}

                    <span className={cn(
                        "truncate flex-1 font-medium tracking-tight", 
                        isViewed && !node.is_dir && "text-muted-foreground"
                    )}>
                        {node.name}
                    </span>

                    {!node.is_dir && (
                        <div className="ml-2 flex items-center gap-1.5">
                            {node.operation === "ADD" && (
                                <span className="px-1.5 py-0.5 rounded-[4px] bg-emerald-500/10 text-emerald-600 text-[9px] font-black uppercase tracking-tighter border border-emerald-500/20">
                                    ADD
                                </span>
                            )}
                            {node.operation === "EDIT" && (
                                <span className="px-1.5 py-0.5 rounded-[4px] bg-amber-500/10 text-amber-600 text-[9px] font-black uppercase tracking-tighter border border-amber-500/20">
                                    MOD
                                </span>
                            )}
                            {node.operation === "DELETE" && (
                                <span className="px-1.5 py-0.5 rounded-[4px] bg-red-500/10 text-red-600 text-[9px] font-black uppercase tracking-tighter border border-red-500/20">
                                    DEL
                                </span>
                            )}
                            {isViewed && <Check className="h-3 w-3 text-emerald-500" />}
                        </div>
                    )}
                </div>

                {node.is_dir && isOpen && (
                    <div className="mt-0.5 relative">
                        {/* Vertical Guide Line */}
                        <div 
                            className="absolute left-[18px] top-0 bottom-0 w-px bg-border/40" 
                            style={{ left: `${level * 16 + 18}px` }}
                        />
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
