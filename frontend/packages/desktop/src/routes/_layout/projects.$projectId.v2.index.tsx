import { createFileRoute, redirect } from "@tanstack/react-router"

export const Route = createFileRoute("/_layout/projects/$projectId/v2/")({
  beforeLoad: ({ params }) => {
    throw redirect({
      to: "/projects/$projectId/v2/assets",
      params: { projectId: params.projectId },
    })
  },
})
