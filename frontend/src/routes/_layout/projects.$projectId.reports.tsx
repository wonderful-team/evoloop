import { createFileRoute } from '@tanstack/react-router'
import { useTranslation } from "react-i18next"

// @ts-ignore
export const Route = createFileRoute('/_layout/projects/$projectId/reports')({
    component: ReportsPage,
})

function ReportsPage() {
    const { t } = useTranslation()
    const { projectId } = Route.useParams()

    return (
        <div className="p-8 flex flex-col items-center justify-center h-full text-muted-foreground">
            <h2 className="text-2xl font-bold mb-2">{t('projects.tabs.reports')}</h2>
            <p>Reports UI for Project #{projectId} coming soon.</p>
        </div>
    )
}
