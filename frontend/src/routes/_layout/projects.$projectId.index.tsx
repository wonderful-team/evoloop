import { createFileRoute } from '@tanstack/react-router'
import { ProjectOverview } from '@/components/Projects/Modules/Overview/ProjectOverview'

export const Route = createFileRoute('/_layout/projects/$projectId/')({
    component: ProjectOverview,
})
