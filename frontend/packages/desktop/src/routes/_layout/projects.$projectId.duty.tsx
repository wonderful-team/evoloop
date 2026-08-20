import { createFileRoute, useParams } from "@tanstack/react-router"
import { ProjectDutyCard } from "@/components/Projects/Modules/Overview/ProjectDutyCard"

export const Route = createFileRoute("/_layout/projects/$projectId/duty")({
  component: DutyPageRoute,
})

function DutyPageRoute() {
  const { projectId } = useParams({ from: "/_layout/projects/$projectId/duty" })

  return (
    <div className="h-full w-full overflow-auto p-6 space-y-6">
      <div className="max-w-7xl mx-auto w-full">
        <ProjectDutyCard projectId={Number(projectId)} />
      </div>
    </div>
  )
}
