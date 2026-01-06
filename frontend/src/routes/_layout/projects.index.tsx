import { createFileRoute } from "@tanstack/react-router"
import { ProjectList } from "@/components/Projects/ProjectList"

export const Route = createFileRoute("/_layout/projects/")({
  component: ProjectList,
})
