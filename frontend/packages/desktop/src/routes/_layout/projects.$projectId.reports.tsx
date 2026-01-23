import { createFileRoute } from "@tanstack/react-router"
import { useTranslation } from "react-i18next"

export const Route = createFileRoute("/_layout/projects/$projectId/reports")({
  component: ReportsPage,
})

function ReportsPage() {
  const { t } = useTranslation()
  const { projectId } = Route.useParams()

  return (
    <div className="h-full w-full overflow-auto p-6 space-y-6">
      <div className="space-y-4">
        <h2 className="text-xl font-semibold tracking-tight">
          {t("projects.tabs.reports")}
        </h2>

        <div className="bg-muted/10 border-2 border-dashed rounded-lg p-12 flex flex-col items-center justify-center text-muted-foreground">
          <div className="bg-muted rounded-full p-4 mb-4">
            {/* PieChart icon would be imported here but we just use text for now to match simplicity */}
            <svg
              xmlns="http://www.w3.org/2000/svg"
              width="24"
              height="24"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="2"
              strokeLinecap="round"
              strokeLinejoin="round"
              className="h-8 w-8 opacity-50"
            >
              <path d="M21.21 15.89A10 10 0 1 1 8 2.83" />
              <path d="M22 12A10 10 0 0 0 12 2v10z" />
            </svg>
          </div>
          <h3 className="text-lg font-medium mb-1">
            {t("projects.reports.comingSoon")}
          </h3>
          <p className="max-w-md text-center">
            {t("projects.reports.description", { id: projectId })}
          </p>
        </div>
      </div>
    </div>
  )
}
