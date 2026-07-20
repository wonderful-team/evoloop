import { createFileRoute, redirect } from "@tanstack/react-router"

export const Route = createFileRoute("/_layout/projects/$projectId/wiki")({
  beforeLoad: ({ params }) => {
    throw redirect({
      to: "/projects/$projectId/knowledge",
      params: { projectId: params.projectId },
    })
  },
})
