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
import { toast } from "sonner"
import { ProjectsService } from "@/client/sdk.gen"
import { MarkdownRenderer } from "@/components/Common/MarkdownRenderer"

export const Route = createFileRoute("/_layout/projects/$projectId/summary")({
  component: SummaryPage,
})

function SummaryPage() {
  const { projectId } = useParams({ from: "/_layout/projects/$projectId" })
  const { t } = useTranslation()
  const [content, setContent] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    const load = async () => {
      if (!projectId) return
      setLoading(true)
      try {
        const data = await ProjectsService.getGenerationContentEndpoint({
          projectId: Number(projectId),
          item: "summary",
        })
        setContent(data.content ?? null)
      } catch (err) {
        console.error("Failed to load summary content", err)
        toast.error(t("common.loadFailed"))
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

  return (
    <div className="h-full w-full overflow-auto p-6 space-y-6">
      <div className="flex items-center gap-3">
        <FileText className="h-6 w-6 text-primary" />
        <h2 className="text-2xl font-bold tracking-tight">
          {t("generation.artifacts.summary")}
        </h2>
      </div>

      {content ? (
        <Card>
          <CardHeader>
            <CardTitle className="text-sm font-medium text-muted-foreground">
              {t("projects.overview.title")}
            </CardTitle>
          </CardHeader>
          <CardContent>
            <MarkdownRenderer content={content} />
          </CardContent>
        </Card>
      ) : (
        <div className="flex flex-col items-center justify-center py-20 text-muted-foreground">
          <AlertCircle className="h-12 w-12 mb-4 opacity-20" />
          <h3 className="text-lg font-medium">
            {t("common.notFound.title")}
          </h3>
          <p className="text-sm max-w-md text-center mt-2">
            {t("generation.description")}
          </p>
        </div>
      )}
    </div>
  )
}
