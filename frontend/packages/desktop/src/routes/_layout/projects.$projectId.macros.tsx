import { createFileRoute, redirect } from "@tanstack/react-router"

export const Route = createFileRoute("/_layout/projects/$projectId/macros")({
  beforeLoad: ({ params }) => {
    throw redirect({
      to: "/projects/$projectId/workflows",
      params: { projectId: params.projectId },
    })
  },
})
