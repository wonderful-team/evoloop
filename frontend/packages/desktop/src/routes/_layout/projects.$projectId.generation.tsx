import { createFileRoute } from "@tanstack/react-router"

import { GenerationPanel } from "@/components/Generation/GenerationPanel"

export const Route = createFileRoute("/_layout/projects/$projectId/generation")(
  {
    component: GenerationPage,
  },
)

function GenerationPage() {
  return <GenerationPanel />
}
