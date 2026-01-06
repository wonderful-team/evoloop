import { createFileRoute } from "@tanstack/react-router"
import { TimesheetList } from "@/components/Projects/Modules/Timesheet/TimesheetList"

export const Route = createFileRoute("/_layout/projects/$projectId/timesheet")({
  component: TimesheetList,
})
