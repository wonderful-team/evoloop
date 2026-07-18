import { createFileRoute, useParams } from "@tanstack/react-router"
import { AppMapPanel } from "@/components/AppMap/AppMapPanel"

export const Route = createFileRoute("/_layout/projects/$projectId/appmap")({
  component: AppMapPage,
})

function AppMapPage() {
  const { projectId } = Route.useParams()
  return <AppMapPanel projectId={projectId} />
}
