import { createFileRoute } from '@tanstack/react-router'
import { GanttChart } from '@/components/Projects/Modules/Gantt/GanttChart'

export const Route = createFileRoute('/_layout/projects/$projectId/gantt')({
    component: GanttChart,
})
