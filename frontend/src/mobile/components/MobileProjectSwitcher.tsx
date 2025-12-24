import { useState, useEffect } from "react"
import { Check, ChevronsUpDown, FolderOpen, Search } from "lucide-react"
import { cn } from "@/lib/utils"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { EvoLoopApi } from "@/client/evoloopClient"
import { toast } from "sonner"
import { Sheet, SheetContent, SheetHeader, SheetTitle, SheetTrigger } from "@/components/ui/sheet"

interface MobileProjectSwitcherProps {
    project?: any;
    onProjectChange?: (project: any) => void;
    onLoaded?: (project: any) => void;
}

export function MobileProjectSwitcher({ project, onProjectChange, onLoaded }: MobileProjectSwitcherProps) {
    const [open, setOpen] = useState(false)
    const [projects, setProjects] = useState<any[]>([])
    const [internalProject, setInternalProject] = useState<any>(null)
    const [searchQuery, setSearchQuery] = useState("")

    const displayProject = project || internalProject

    // Fetch Projects and Init
    useEffect(() => {
        let isMounted = true;
        const init = async () => {
            // Only fetch list if empty? Or always refresh? Always refresh is safer.
            try {
                const listRes = await EvoLoopApi.getCloudProjects({ page: 1, page_size: 100 })

                if (!isMounted) return;

                if (listRes && Array.isArray(listRes.list)) {
                    setProjects(listRes.list)
                }

                // If no external project provided, try to fetch current from Server or default to first
                if (!project) {
                    const currentRes = await EvoLoopApi.getCloudCurrentProject()
                    if (currentRes) {
                        setInternalProject(currentRes)
                        onProjectChange?.(currentRes) // Sync up
                        onLoaded?.(currentRes)
                    } else if (listRes && Array.isArray(listRes.list) && listRes.list.length > 0) {
                        const first = listRes.list[0];
                        setInternalProject(first)
                        onProjectChange?.(first)
                        onLoaded?.(first)
                    }
                }
            } catch (e) {
                console.error("Failed to load projects", e)
            }
        }
        init()
        return () => { isMounted = false; }
    }, []) // Run once on mount

    // Sync internal if prop changes (not strictly needed since we use displayProject, but good for consistency)
    useEffect(() => {
        if (project) {
            setInternalProject(project)
        }
    }, [project])

    const handleSelect = async (selected: any) => {
        if (displayProject?.project_id === selected.project_id) {
            setOpen(false)
            return
        }

        // Optimistic update
        const old = displayProject
        setInternalProject(selected) // Update internal immediately
        onProjectChange?.(selected) // Notify parent
        setOpen(false)

        toast.info(`Switching to ${selected.project_name}...`)

        try {
            await EvoLoopApi.switchCloudProject(selected.project_id)
            toast.success(`Switched to ${selected.project_name}`)
        } catch (e: any) {
            setInternalProject(old)
            onProjectChange?.(old)
            toast.error("Failed to switch: " + e.message)
        }
    }

    const filteredProjects = projects.filter(p =>
        p.project_name.toLowerCase().includes(searchQuery.toLowerCase())
    )

    return (
        <Sheet open={open} onOpenChange={setOpen}>
            <SheetTrigger asChild>
                <Button
                    variant="ghost"
                    className="h-auto p-1 hover:bg-transparent gap-2"
                >
                    <div className="flex flex-col items-start">
                        <span className="text-[10px] text-muted-foreground leading-none mb-0.5">Project</span>
                        <div className="flex items-center gap-1">
                            <span className="font-semibold text-sm truncate max-w-[140px]">
                                {displayProject?.project_name || "Select"}
                            </span>
                            <ChevronsUpDown className="h-3 w-3 opacity-50" />
                        </div>
                    </div>
                </Button>
            </SheetTrigger>
            <SheetContent side="bottom" className="h-[80vh] flex flex-col p-4 rounded-t-[10px]">
                <SheetHeader className="mb-4">
                    <SheetTitle>Switch Project</SheetTitle>
                </SheetHeader>

                <div className="relative mb-4">
                    <Search className="absolute left-2 top-2.5 h-4 w-4 text-muted-foreground" />
                    <Input
                        placeholder="Search project..."
                        value={searchQuery}
                        onChange={(e) => setSearchQuery(e.target.value)}
                        className="pl-8"
                    />
                </div>

                <div className="flex-1 overflow-y-auto -mx-4 px-4">
                    <div className="space-y-1 pb-6">
                        {filteredProjects.length === 0 ? (
                            <div className="text-center py-8 text-sm text-muted-foreground">
                                No projects found.
                            </div>
                        ) : (
                            filteredProjects.map((p) => (
                                <div
                                    key={p.project_id}
                                    className={cn(
                                        "flex items-center justify-between p-3 rounded-lg border",
                                        displayProject?.project_id === p.project_id
                                            ? "bg-primary/10 border-primary/50"
                                            : "bg-background border-border"
                                    )}
                                    onClick={() => handleSelect(p)}
                                >
                                    <div className="flex items-center gap-3 overflow-hidden">
                                        <div className="bg-muted p-2 rounded-md shrink-0">
                                            <FolderOpen className="h-4 w-4" />
                                        </div>
                                        <div className="flex flex-col overflow-hidden">
                                            <span className="font-medium text-sm truncate">{p.project_name}</span>
                                            <span className="text-xs text-muted-foreground truncate">{p.project_desc || "No description"}</span>
                                        </div>
                                    </div>
                                    {displayProject?.project_id === p.project_id && (
                                        <Check className="h-4 w-4 text-primary shrink-0" />
                                    )}
                                </div>
                            ))
                        )}
                    </div>
                </div>
            </SheetContent>
        </Sheet>
    )
}
