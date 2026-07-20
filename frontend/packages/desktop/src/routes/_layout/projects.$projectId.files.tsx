import { createFileRoute, redirect } from "@tanstack/react-router"

export const Route = createFileRoute("/_layout/projects/$projectId/files")({
  beforeLoad: ({ params }) => {
    throw redirect({
      to: "/projects/$projectId/assets",
      params: { projectId: params.projectId },
    })
  },
})
