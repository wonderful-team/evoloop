import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
} from "@evoloop/shared/components/ui/card"
import { createFileRoute, useParams } from "@tanstack/react-router"
import { AlertCircle, FileText, Loader2 } from "lucide-react"
import { useEffect, useState } from "react"
import { useTranslation } from "react-i18next"
import { ProjectProfilesService, ProjectsService } from "@/client"
import { MarkdownRenderer } from "@/components/Common/MarkdownRenderer"

interface SummaryData {
  description: string
  technical_stack: string[]
  core_features: string[]
}

export const Route = createFileRoute("/_layout/projects/$projectId/overview")({
  component: OverviewPage,
})

function OverviewPage() {
  const { projectId } = useParams({ from: "/_layout/projects/$projectId" })
  const { t } = useTranslation()
  const [summary, setSummary] = useState<SummaryData | null>(null)
  const [profileContent, setProfileContent] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    const load = async () => {
      if (!projectId) return
      setLoading(true)
      try {
        const [profileRes, summaryRes] = await Promise.all([
          ProjectProfilesService.projectsGetProfile({ projectId: Number(projectId) }),
          ProjectsService.getGenerationContentEndpoint({
            projectId: Number(projectId),
            item: "summary",
          }).catch(() => ({ content: null })),
        ])
        setProfileContent(profileRes.content ?? null)

        if (summaryRes?.content) {
          try {
            setSummary(JSON.parse(summaryRes.content))
          } catch {
            setSummary(null)
          }
        }
      } catch (err) {
        console.error("Failed to load overview", err)
      } finally {
        setLoading(false)
      }
    }
    load()
  }, [projectId])

  if (loading) {
    return (
      <div className="flex items-center justify-center h-full">
        <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
      </div>
    )
  }

  const hasAny = summary || profileContent

  return (
    <div className="h-full w-full overflow-auto p-6 space-y-6">
      <div className="flex items-center gap-3">
        <FileText className="h-6 w-6 text-primary" />
        <h2 className="text-2xl font-bold tracking-tight">
          {t("generation.artifacts.overview")}
        </h2>
      </div>

      {!hasAny ? (
        <div className="flex flex-col items-center justify-center py-20 text-muted-foreground">
          <AlertCircle className="h-12 w-12 mb-4 opacity-20" />
          <h3 className="text-lg font-medium">{t("projects.profile.notFound")}</h3>
          <p className="text-sm max-w-md text-center mt-2">
            {t("projects.profile.notFoundDescription")}
          </p>
        </div>
      ) : (
        <>
          {summary && (
            <Card>
              <CardHeader>
                <CardTitle className="text-base">
                  {t("generation.summaryTitle", "项目摘要")}
                </CardTitle>
              </CardHeader>
              <CardContent className="space-y-4">
                <p className="text-sm">{summary.description}</p>
                {summary.technical_stack && summary.technical_stack.length > 0 && (
                  <div>
                    <p className="text-xs font-medium text-muted-foreground mb-1">
                      {t("generation.techStack", "技术栈")}
                    </p>
                    <div className="flex flex-wrap gap-1">
                      {summary.technical_stack.map((s: string) => (
                        <span key={s} className="text-xs bg-secondary text-secondary-foreground px-2 py-0.5 rounded">
                          {s}
                        </span>
                      ))}
                    </div>
                  </div>
                )}
                {summary.core_features && summary.core_features.length > 0 && (
                  <div>
                    <p className="text-xs font-medium text-muted-foreground mb-1">
                      {t("generation.coreFeatures", "核心功能")}
                    </p>
                    <ul className="list-disc list-inside text-sm space-y-0.5">
                      {summary.core_features.map((f: string) => (
                        <li key={f}>{f}</li>
                      ))}
                    </ul>
                  </div>
                )}
              </CardContent>
            </Card>
          )}

          {profileContent && (
            <Card>
              <CardHeader>
                <CardTitle className="text-sm font-medium text-muted-foreground">
                  {t("projects.profile.documentTitle")}
                </CardTitle>
              </CardHeader>
              <CardContent>
                <MarkdownRenderer content={profileContent} />
              </CardContent>
            </Card>
          )}
        </>
      )}
    </div>
  )
}
