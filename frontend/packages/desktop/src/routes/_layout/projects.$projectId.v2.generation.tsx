import { createFileRoute, redirect } from "@tanstack/react-router"

export const Route = createFileRoute("/_layout/projects/$projectId/v2/generation")({
  beforeLoad: ({ params }) => {
    throw redirect({
      to: "/projects/$projectId",
      params: { projectId: params.projectId },
    })
  },
})
