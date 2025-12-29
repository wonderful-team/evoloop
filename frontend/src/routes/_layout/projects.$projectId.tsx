import { createFileRoute, Outlet, Link } from '@tanstack/react-router'
import { useProjectStore } from "@/stores/projectStore"
import { useEffect } from "react"
import {
    Folder, FileCode, CheckSquare, BarChart2,
    PieChart, Clock, AlertCircle, ChevronLeft
} from "lucide-react"
import { useTranslation } from "react-i18next"

export const Route = createFileRoute('/_layout/projects/$projectId')({
    component: ProjectLayout,
})

function ProjectLayout() {
    const { projectId } = Route.useParams()
    const { currentProject, projects, fetchProjects, setProject } = useProjectStore()
    // location unused
    // const location = useLocation()
    const { t } = useTranslation()

    // Sync params with store on mount or update
    useEffect(() => {
        if (!projectId) return

        // If we have projects but current doesn't match, find and set
        if (projects.length > 0) {
            const p = projects.find(p => p.id === Number(projectId))
            if (p) {
                if (p.id !== currentProject?.id) {
                    setProject(p)
                }
            } else {
                // Not found in local store, maybe fetch fresh?
                fetchProjects()
            }
        } else {
            // If no projects loaded (e.g. refresh), fetch them
            fetchProjects()
        }
    }, [projectId, projects, currentProject, fetchProjects, setProject])

    const displayProject = currentProject?.id === Number(projectId) ? currentProject : projects.find(p => p.id === Number(projectId))

    if (!displayProject && projects.length > 0) {
        return (
            <div className="flex flex-col items-center justify-center h-[calc(100vh-8rem)] text-muted-foreground">
                <AlertCircle className="h-12 w-12 mb-4 opacity-20" />
                <h3 className="text-lg font-medium">{t('common.notFound.title')}</h3>
                <p>{t('projects.noProjects')}</p>
            </div>
        )
    }

    const tabs = [
        // Overview Dashboard (Future)
        // { id: 'overview', label: t('projects.tabs.overview'), icon: LayoutDashboard, path: '' }, 

        { id: 'files', label: t('projects.tabs.files'), icon: FileCode, path: '/files' },
        { id: 'tasks', label: t('projects.tabs.tasks'), icon: CheckSquare, path: '/tasks' },
        { id: 'gantt', label: t('projects.tabs.gantt'), icon: BarChart2, path: '/gantt' },
        { id: 'timesheet', label: t('projects.tabs.timesheet'), icon: Clock, path: '/timesheet' },
        { id: 'reports', label: t('projects.tabs.reports'), icon: PieChart, path: '/reports' },
    ]

    return (
        <div className="flex flex-col h-[calc(100vh-4rem)]">
            {/* Header / Tabs */}
            <div className="border-b bg-background px-4">
                <div className="flex items-center h-12 gap-4">
                    <div className="flex items-center gap-2 font-semibold text-sm min-w-[200px]">
                        <Link to="/projects" className="p-1 -ml-1 rounded hover:bg-muted text-muted-foreground hover:text-foreground transition-colors" title={t('projects.backToList')}>
                            <Folder className="h-4 w-4 hidden" /> {/* Original icon hidden or removed if replaced by back arrow, let's keep it clean */}
                            <ChevronLeft className="h-5 w-5" />
                        </Link>
                        <span className="truncate max-w-[150px]">{displayProject?.name || `Project #${projectId}`}</span>
                    </div>

                    <div className="h-6 w-px bg-border mx-2" />

                    <nav className="flex items-center gap-1">
                        {tabs.map((tab) => {
                            const fullPath = `/projects/${projectId}${tab.path}`
                            // Check active. Exact match for empty path, startsWith for others
                            // Actually tanstack router link handles active state well
                            return (
                                <Link
                                    key={tab.id}
                                    to={fullPath}
                                    className="flex items-center gap-2 px-3 py-1.5 text-sm font-medium rounded-md transition-colors text-muted-foreground hover:text-foreground hover:bg-muted/50 data-[status=active]:bg-primary/10 data-[status=active]:text-primary"
                                    activeProps={{
                                        'data-status': 'active',
                                    }}
                                >
                                    <tab.icon className="h-4 w-4" />
                                    {tab.label}
                                </Link>
                            )
                        })}
                    </nav>
                </div>
            </div>

            {/* Content Outlet */}
            <div className="flex-1 overflow-hidden relative">
                <Outlet />
            </div>
        </div>
    )
}
