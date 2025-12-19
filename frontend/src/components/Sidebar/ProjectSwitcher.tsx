import * as React from "react"
import { ChevronsUpDown, Plus, Folder } from "lucide-react"

import {
    DropdownMenu,
    DropdownMenuContent,
    DropdownMenuItem,
    DropdownMenuLabel,
    DropdownMenuSeparator,
    DropdownMenuShortcut,
    DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu"
import {
    SidebarMenu,
    SidebarMenuButton,
    SidebarMenuItem,
    useSidebar,
} from "@/components/ui/sidebar"
import { useProjectStore } from "@/stores/projectStore"
import { useNavigate } from "@tanstack/react-router"

export function ProjectSwitcher() {
    const { isMobile } = useSidebar()
    const { projects, currentProject, setProject, fetchProjects } = useProjectStore()
    const navigate = useNavigate()

    // Initial fetch if needed, though App might handle it later
    // Better to ensure it's loaded
    React.useEffect(() => {
        if (projects.length === 0) {
            fetchProjects()
        }
    }, [])

    return (
        <SidebarMenu>
            <SidebarMenuItem>
                <DropdownMenu>
                    <DropdownMenuTrigger asChild>
                        <SidebarMenuButton
                            size="lg"
                            className="data-[state=open]:bg-sidebar-accent data-[state=open]:text-sidebar-accent-foreground"
                        >
                            <div className="flex aspect-square size-8 items-center justify-center rounded-lg bg-sidebar-primary text-sidebar-primary-foreground">
                                <Folder className="size-4" />
                            </div>
                            <div className="grid flex-1 text-left text-sm leading-tight">
                                <span className="truncate font-semibold">
                                    {currentProject?.name || "Select Project"}
                                </span>
                                <span className="truncate text-xs">
                                    {currentProject?.status_text || "EvoLoop"}
                                </span>
                            </div>
                            <ChevronsUpDown className="ml-auto" />
                        </SidebarMenuButton>
                    </DropdownMenuTrigger>
                    <DropdownMenuContent
                        className="w-[--radix-dropdown-menu-trigger-width] min-w-56 rounded-lg"
                        align="start"
                        side={isMobile ? "bottom" : "right"}
                        sideOffset={4}
                    >
                        <DropdownMenuLabel className="text-xs text-muted-foreground">
                            Projects
                        </DropdownMenuLabel>
                        {projects.map((project) => (
                            <DropdownMenuItem
                                key={project.id}
                                onClick={() => setProject(project)}
                                className="gap-2 p-2"
                            >
                                <div className="flex size-6 items-center justify-center rounded-sm border">
                                    <Folder className="size-4 shrink-0" />
                                </div>
                                {project.name}
                                <DropdownMenuShortcut>⌘{project.id}</DropdownMenuShortcut>
                            </DropdownMenuItem>
                        ))}
                        <DropdownMenuSeparator />
                        <DropdownMenuItem className="gap-2 p-2" onClick={() => navigate({ to: '/projects' })}>
                            <div className="flex size-6 items-center justify-center rounded-sm border bg-background">
                                <Plus className="size-4" />
                            </div>
                            <div className="font-medium text-muted-foreground">More Projects</div>
                        </DropdownMenuItem>
                    </DropdownMenuContent>
                </DropdownMenu>
            </SidebarMenuItem>
        </SidebarMenu>
    )
}
