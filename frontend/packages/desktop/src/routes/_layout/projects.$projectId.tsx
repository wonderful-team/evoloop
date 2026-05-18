import { createFileRoute, Link, Outlet, redirect } from "@tanstack/react-router"
import { isLoggedIn } from "@/hooks/useAuth"
import {
  AlertCircle,
  BarChart2,
  BookOpen,
  CheckSquare,
  ChevronLeft,
  ClipboardList,
  Clock,
  FileCode,
  FileText,
  LayoutDashboard,
} from "lucide-react"
import { useEffect } from "react"
import { useTranslation } from "react-i18next"
import { useProjectStore } from "@/stores/projectStore"

export const Route = createFileRoute("/_layout/projects/$projectId")({
  component: ProjectLayout,
  beforeLoad: async () => {
    if (!isLoggedIn()) {
      throw redirect({ to: "/login" })
    }
  },
})

function ProjectLayout() {
  const { projectId } = Route.useParams()
  const { currentProject, projects, fetchProjects, setProject } =
    useProjectStore()
  // location unused
  // const location = useLocation()
  const { t } = useTranslation()

  // Sync params with store on mount or update
  useEffect(() => {
    if (!projectId) return

    // If we have projects but current doesn't match, find and set
    if (projects.length > 0) {
      const p = projects.find((p) => p.id === Number(projectId))
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

  const displayProject =
    currentProject?.id === Number(projectId)
      ? currentProject
      : projects.find((p) => p.id === Number(projectId))

  if (!displayProject && projects.length > 0) {
    return (
      <div className="flex flex-col items-center justify-center h-[calc(100vh-8rem)] text-muted-foreground">
        <AlertCircle className="h-12 w-12 mb-4 opacity-20" />
        <h3 className="text-lg font-medium">{t("common.notFound.title")}</h3>
        <p>{t("projects.noProjects")}</p>
      </div>
    )
  }

  const tabs = [
    {
      id: "overview",
      label: t("projects.tabs.overview"),
      icon: LayoutDashboard,
      path: "",
    },
    {
      id: "files",
      label: t("projects.tabs.files"),
      icon: FileCode,
      path: "/files",
    },
    {
      id: "tasks",
      label: t("projects.tabs.tasks"),
      icon: CheckSquare,
      path: "/tasks",
    },
    {
      id: "wiki",
      label: t("projects.tabs.wiki"),
      icon: FileText,
      path: "/wiki",
    },
    {
      id: "knowledge",
      label: t("projects.tabs.knowledge"),
      icon: BookOpen,
      path: "/knowledge",
    },
    {
      id: "profile",
      label: t("projects.tabs.profile"),
      icon: FileText,
      path: "/profile",
    },
    // { id: 'reports', label: t('projects.tabs.reports'), icon: PieChart, path: '/reports' },
  ]

  return (
    <div className="flex h-full w-full">
      {/* Project Sidebar */}
      <aside className="w-60 border-r border-border bg-muted/10 flex flex-col shrink-0">
        <div className="h-14 flex items-center gap-2 px-4 border-b border-border">
          <Link
            to="/projects"
            className="p-1.5 -ml-1.5 rounded-md hover:bg-muted text-muted-foreground hover:text-foreground transition-colors"
            title={t("projects.backToList")}
          >
            <ChevronLeft className="h-4 w-4" />
          </Link>
          <span
            className="font-semibold text-sm truncate"
            title={displayProject?.name}
          >
            {displayProject?.name || `Project #${projectId}`}
          </span>
        </div>

        <nav className="flex-1 p-3 space-y-1 overflow-y-auto">
          {tabs.map((tab) => {
            const fullPath = `/projects/${projectId}${tab.path}`
            return (
              <Link
                key={tab.id}
                to={fullPath}
                className="flex items-center gap-3 px-3 py-2 text-sm font-medium rounded-md transition-colors text-muted-foreground hover:text-foreground hover:bg-muted data-[status=active]:bg-primary data-[status=active]:text-primary-foreground"
                activeProps={{
                  "data-status": "active",
                }}
                activeOptions={{ exact: true }}
              >
                <tab.icon className="h-4 w-4" />
                {tab.label}
              </Link>
            )
          })}
        </nav>
      </aside>

      {/* Content Outlet */}
      <main className="flex-1 overflow-hidden relative bg-background">
        <Outlet />
      </main>
    </div>
  )
}
