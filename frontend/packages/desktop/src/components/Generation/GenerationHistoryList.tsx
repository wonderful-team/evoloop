import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
} from "@evoloop/shared/components/ui/card"
import { Link, useParams } from "@tanstack/react-router"
import { Eye, RefreshCw } from "lucide-react"
import { Button } from "@evoloop/shared/components/ui/button"
import { useTranslation } from "react-i18next"
import type { GenerationStatusRecord } from "@/client"
import { GenerationStatusBadge } from "./GenerationStatusBadge"

const ARTIFACT_ROUTE: Record<string, string> = {
  wiki: "wiki",
  appmap: "appmap",
  summary: "summary",
  overview: "overview",
}

interface GenerationHistoryListProps {
  statuses: Record<string, GenerationStatusRecord>
  onRetry: (item: string) => void
}

export function GenerationHistoryList({
  statuses,
  onRetry,
}: GenerationHistoryListProps) {
  const { projectId } = useParams({ from: "/_layout/projects/$projectId" })
  const { t } = useTranslation()

  const completed = Object.values(statuses).filter(
    (s) => s.status === "completed" || s.status === "failed",
  )

  if (completed.length === 0) {
    return null
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-lg">
          {t("common.history", { defaultValue: "History" })}
        </CardTitle>
      </CardHeader>
      <CardContent>
        <div className="space-y-2">
          {completed.map((record) => (
            <div
              key={record.item}
              className="flex items-center justify-between border rounded-lg px-4 py-3"
            >
              <div className="flex items-center gap-3">
                <span className="text-sm font-medium capitalize">
                  {t(`generation.artifacts.${record.item}`, {
                    defaultValue: record.item,
                  })}
                </span>
                <GenerationStatusBadge status={record.status} />
              </div>
              <div className="flex items-center gap-2">
                {record.status === "completed" && ARTIFACT_ROUTE[record.item] && (
                  <Link
                    to={`/projects/$projectId/${ARTIFACT_ROUTE[record.item]}` as any}
                    params={{ projectId: projectId! } as any}
                  >
                    <Button variant="ghost" size="icon" title={t("common.preview")}>
                      <Eye className="h-4 w-4" />
                    </Button>
                  </Link>
                )}
                {record.status === "failed" && (
                  <Button
                    variant="ghost"
                    size="icon"
                    onClick={() => onRetry(record.item)}
                    title={t("generation.retry")}
                  >
                    <RefreshCw className="h-4 w-4" />
                  </Button>
                )}
              </div>
            </div>
          ))}
        </div>
      </CardContent>
    </Card>
  )
}
