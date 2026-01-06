import { createFileRoute } from "@tanstack/react-router"
import { TaskList } from "@/components/Projects/Modules/Tasks/TaskList"

export const Route = createFileRoute("/_layout/projects/$projectId/tasks")({
  component: TaskList,
})
