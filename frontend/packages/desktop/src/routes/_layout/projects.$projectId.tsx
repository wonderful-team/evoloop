import { createFileRoute, Outlet, redirect } from "@tanstack/react-router"
import { AlertCircle } from "lucide-react"
import { useEffect } from "react"
import { useTranslation } from "react-i18next"
import { ProjectSidebar } from "@/components/Projects/Redesign/Sidebar/ProjectSidebar"
import { isLoggedIn } from "@/hooks/useAuth"
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
  const { t } = useTranslation()

  // Sync params with store on mount or update
  useEffect(() => {
    if (!projectId) return

    if (projects.length > 0) {
      const p = projects.find((p) => p.id === Number(projectId))
      if (p) {
        if (p.id !== currentProject?.id) {
          setProject(p)
        }
      } else {
        fetchProjects()
      }
    } else {
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

  return (
    <div className="flex h-full w-full overflow-hidden bg-background">
      {/* Project Redesigned Sidebar */}
      <ProjectSidebar
        currentProject={displayProject}
        projects={projects}
        indexingStatus={displayProject?.indexing_status || "synced"}
      />

      {/* Main Content Workspace Outlet */}
      <main className="flex-1 overflow-hidden relative bg-background flex flex-col">
        <Outlet />
      </main>
    </div>
  )
}
