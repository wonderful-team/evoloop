import { useState, useEffect } from "react"
import { Check, ChevronsUpDown, FolderOpen, Search } from "lucide-react"
import { cn } from "@/lib/utils"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { EvoLoopApi } from "@/client/evoloopClient"
import { toast } from "sonner"
import { Sheet, SheetContent, SheetHeader, SheetTitle, SheetTrigger } from "@/components/ui/sheet"

interface MobileProjectSwitcherProps {
    onProjectChange?: (project: any) => void;
    onLoaded?: (project: any) => void;
}

export function MobileProjectSwitcher({ onProjectChange, onLoaded }: MobileProjectSwitcherProps) {
    const [open, setOpen] = useState(false)
    const [projects, setProjects] = useState<any[]>([])
    const [currentProject, setCurrentProject] = useState<any>(null)
    const [searchQuery, setSearchQuery] = useState("")

    // Fetch Projects and Current Project
    useEffect(() => {
        let isMounted = true;
        const init = async () => {
            let initialProject = null;
            try {
                // Parallel fetch
                const [listRes, currentRes] = await Promise.all([
                    EvoLoopApi.getCloudProjects({ page: 1, page_size: 100 }), // Get all or enough
                    EvoLoopApi.getCloudCurrentProject()
                ])

                if (!isMounted) return;

                if (listRes && Array.isArray(listRes.list)) {
                    setProjects(listRes.list)
                }

                if (currentRes) {
                    setCurrentProject(currentRes)
                    initialProject = currentRes;
                } else if (listRes && Array.isArray(listRes.list) && listRes.list.length > 0) {
                    // Auto-select first project if none active
                    const first = listRes.list[0];
                    setCurrentProject(first);
                    initialProject = first;
                    // Optional: Persist switching to cloud? 
                    // To match desktop behavior, we should probably switch, but let's just use it for now to avoid side effects during init
                    // Or maybe we should? If we don't switch, next time it will be null again.
                    // But init shouldn't trigger heavy side effects. Let's just set context.
                }
            } catch (e) {
                console.error("Failed to load projects", e)
            } finally {
                if (isMounted) {
                    onLoaded?.(initialProject)
                }
            }
        }
        init()
        return () => { isMounted = false; }
    }, [])

    const handleSelect = async (project: any) => {
        if (currentProject?.project_id === project.project_id) {
            setOpen(false)
            return
        }

        // Optimistic update? Better wait for confirm
        const old = currentProject
        setCurrentProject(project)
        onProjectChange?.(project)
        setOpen(false)

        toast.info(`Switching to ${project.project_name}...`)

        try {
            await EvoLoopApi.switchCloudProject(project.project_id)
            toast.success(`Switched to ${project.project_name}`)
        } catch (e: any) {
            setCurrentProject(old)
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
                                {currentProject?.project_name || "Select"}
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
                            filteredProjects.map((project) => (
                                <div
                                    key={project.project_id}
                                    className={cn(
                                        "flex items-center justify-between p-3 rounded-lg border",
                                        currentProject?.project_id === project.project_id
                                            ? "bg-primary/10 border-primary/50"
                                            : "bg-background border-border"
                                    )}
                                    onClick={() => handleSelect(project)}
                                >
                                    <div className="flex items-center gap-3 overflow-hidden">
                                        <div className="bg-muted p-2 rounded-md shrink-0">
                                            <FolderOpen className="h-4 w-4" />
                                        </div>
                                        <div className="flex flex-col overflow-hidden">
                                            <span className="font-medium text-sm truncate">{project.project_name}</span>
                                            <span className="text-xs text-muted-foreground truncate">{project.project_desc || "No description"}</span>
                                        </div>
                                    </div>
                                    {currentProject?.project_id === project.project_id && (
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
