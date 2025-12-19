import * as React from "react"
import { ChevronsUpDown, Folder, Search, Clock, ListTodo } from "lucide-react"

import {
    Dialog,
    DialogContent,
    DialogDescription,
    DialogHeader,
    DialogTitle,
    DialogTrigger,
} from "@/components/ui/dialog"
import { Badge } from "@/components/ui/badge"
import { Input } from "@/components/ui/input"
import { Button } from "@/components/ui/button"
import { useNavigate } from "@tanstack/react-router"
import { useProjectStore, type Project } from "@/stores/projectStore"
import { cn } from "@/lib/utils"

export function ProjectSwitcher() {
    const { projects, currentProject, setProject, fetchProjects } = useProjectStore()
    const [open, setOpen] = React.useState(false)
    const [searchQuery, setSearchQuery] = React.useState("")

    const navigate = useNavigate()

    React.useEffect(() => {
        if (projects.length === 0) {
            fetchProjects()
        }
    }, [])

    const filteredProjects = projects.filter(project =>
        project.name.toLowerCase().includes(searchQuery.toLowerCase()) ||
        project.description?.toLowerCase().includes(searchQuery.toLowerCase())
    )

    const handleSelect = (project: Project) => {
        setProject(project)
        setOpen(false)
    }

    return (
        <Dialog open={open} onOpenChange={setOpen}>
            <DialogTrigger asChild>
                <Button
                    variant="outline"
                    role="combobox"
                    aria-expanded={open}
                    className="w-[400px] justify-between h-10 px-3 bg-background"
                >
                    <div className="flex items-center gap-2 overflow-hidden">
                        <div className="flex aspect-square size-5 items-center justify-center rounded bg-primary/10 text-primary">
                            <Folder className="size-3.5" />
                        </div>
                        <span className="truncate font-medium">
                            {currentProject?.name || "Select Project"}
                        </span>
                        {currentProject?.status_text && (
                            <Badge variant="secondary" className="ml-2 h-5 text-[10px] px-1.5 font-normal text-muted-foreground hidden sm:inline-flex">
                                {currentProject.status_text}
                            </Badge>
                        )}
                    </div>
                    <ChevronsUpDown className="ml-2 size-4 shrink-0 opacity-50" />
                </Button>
            </DialogTrigger>
            <DialogContent className="sm:max-w-4xl max-h-[80vh] flex flex-col p-0 gap-0 overflow-hidden">
                <div className="p-4 border-b">
                    <DialogHeader className="mb-4">
                        <DialogTitle>Switch Project</DialogTitle>
                        <DialogDescription>
                            Select a project to switch to or manage your projects.
                        </DialogDescription>
                    </DialogHeader>
                    <div className="relative">
                        <Search className="absolute left-2.5 top-2.5 h-4 w-4 text-muted-foreground" />
                        <Input
                            placeholder="Search projects by name or description..."
                            value={searchQuery}
                            onChange={(e) => setSearchQuery(e.target.value)}
                            className="pl-9"
                        />
                    </div>
                </div>

                <div className="overflow-y-auto p-4 flex-1">
                    {filteredProjects.length === 0 ? (
                        <div className="flex h-[300px] flex-col items-center justify-center text-center text-muted-foreground">
                            <Folder className="h-12 w-12 mb-2 opacity-20" />
                            <p>No projects found.</p>
                        </div>
                    ) : (
                        <div className="flex flex-col gap-2">
                            {filteredProjects.map((project) => {
                                const isSelected = currentProject?.id === project.id
                                return (
                                    <div
                                        key={project.id}
                                        onClick={() => handleSelect(project)}
                                        className={cn(
                                            "cursor-pointer rounded-lg border bg-card text-card-foreground shadow-sm transition-all hover:border-primary hover:shadow-md relative group",
                                            isSelected ? "border-primary ring-1 ring-primary" : ""
                                        )}
                                    >
                                        <div className="p-3 flex items-center justify-between gap-4">
                                            <div className="flex-1 min-w-0 space-y-1">
                                                <div className="flex items-center gap-2">
                                                    <h3 className="font-semibold leading-none tracking-tight truncate">
                                                        {project.name}
                                                    </h3>
                                                    <Badge
                                                        variant={project.status === 1 ? "default" : "secondary"}
                                                        className={cn(
                                                            "shrink-0 capitalize text-[10px] px-1.5 py-0 h-5",
                                                            project.status === 1 ? "bg-green-500/15 text-green-700 hover:bg-green-500/25 dark:text-green-400" : ""
                                                        )}
                                                    >
                                                        {project.status_text || 'Unknown'}
                                                    </Badge>
                                                </div>
                                                <p className="text-xs text-muted-foreground truncate font-mono" title={project.path}>
                                                    {project.path}
                                                </p>
                                            </div>

                                            <div className="flex items-center gap-4 text-xs text-muted-foreground shrink-0">
                                                <div className="flex items-center gap-1.5 w-24" title="Tasks">
                                                    <ListTodo className="h-3.5 w-3.5" />
                                                    <span>
                                                        {project.task_stats?.pending || 0} / {project.task_stats?.total || 0} tasks
                                                    </span>
                                                </div>
                                                <div className="flex items-center gap-1.5 w-24 justify-end" title="Last Sync">
                                                    <Clock className="h-3.5 w-3.5" />
                                                    <span>{project.last_sync_time_format?.split(' ')[0] || 'Never'}</span>
                                                </div>
                                            </div>
                                        </div>

                                        {isSelected && (
                                            <div className="absolute left-0 top-0 bottom-0 w-1 rounded-l-lg bg-primary" />
                                        )}
                                    </div>
                                )
                            })}
                        </div>
                    )}
                </div>

                <div className="p-4 border-t bg-muted/50 flex justify-between items-center text-xs text-muted-foreground">
                    <span>Showing {filteredProjects.length} projects</span>
                    <Button variant="ghost" size="sm" className="h-7 text-xs" onClick={() => { setOpen(false); navigate({ to: '/projects' }) }}>
                        Manage Projects
                    </Button>
                </div>
            </DialogContent>
        </Dialog>
    )
}
