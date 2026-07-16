import { createFileRoute, redirect } from "@tanstack/react-router"
import { MacroLibraryView } from "@/components/Learning/MacroLibraryView"
import { isLoggedIn } from "@/hooks/useAuth"

export const Route = createFileRoute("/_layout/projects/$projectId/macros")({
  component: ProjectMacrosRoute,
  beforeLoad: async () => {
    if (!isLoggedIn()) {
      throw redirect({ to: "/login" })
    }
  },
})

function ProjectMacrosRoute() {
  const { projectId } = Route.useParams()

  return (
    <div className="h-full w-full flex flex-col p-6">
      <MacroLibraryView projectId={parseInt(projectId, 10)} />
    </div>
  )
}
