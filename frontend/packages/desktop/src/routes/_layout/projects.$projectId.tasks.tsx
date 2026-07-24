import { createFileRoute } from "@tanstack/react-router"
import { TaskList } from "@/components/Projects/Modules/Tasks/TaskList"

export const Route = createFileRoute("/_layout/projects/$projectId/tasks")({
  component: TasksPageRoute,
})

function TasksPageRoute() {
  return (
    <div className="h-full w-full overflow-auto p-6 space-y-6">
      <div className="max-w-7xl mx-auto w-full">
        <TaskList />
      </div>
    </div>
  )
}
