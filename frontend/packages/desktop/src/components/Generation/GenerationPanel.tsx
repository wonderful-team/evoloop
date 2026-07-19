import { Button } from "@evoloop/shared/components/ui/button"
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
} from "@evoloop/shared/components/ui/card"
import { Checkbox } from "@evoloop/shared/components/ui/checkbox"
import { Link, useParams } from "@tanstack/react-router"
import { Eye, Loader2, Play, RefreshCw } from "lucide-react"
import { useEffect, useState } from "react"
import { useTranslation } from "react-i18next"
import { toast } from "sonner"
import { type GenerationStatusRecord, ProjectsService } from "@/client"
import { ProjectProfilesService } from "@/client/sdk.gen"
import { systemSSEClient } from "@/lib/SystemSSEClient"
import { GenerationStatusBadge } from "./GenerationStatusBadge"
import { GenerationHistoryList } from "./GenerationHistoryList"

const ARTIFACTS = [
  { key: "wiki", labelKey: "generation.artifacts.wiki", route: "wiki" },
  { key: "appmap", labelKey: "generation.artifacts.macros", route: "macros" },
  { key: "overview", labelKey: "generation.artifacts.overview", route: "overview" },
]

const SCHEDULER_ITEMS = new Set(["wiki", "appmap", "overview"])

export function GenerationPanel() {
  const { projectId } = useParams({ from: "/_layout/projects/$projectId" })
  const { t } = useTranslation()
  const [statuses, setStatuses] = useState<
    Record<string, GenerationStatusRecord>
  >({})
  const [selected, setSelected] = useState<string[]>([])
  const [loading, setLoading] = useState(false)
  const [initialLoading, setInitialLoading] = useState(true)

  const fetchStatus = async () => {
    if (!projectId) return
    try {
      const [res, profile] = await Promise.all([
        ProjectsService.listGenerationStatusEndpoint({
          projectId: Number(projectId),
        }),
        ProjectProfilesService.projectsGetProfile({
          projectId: Number(projectId),
        }),
      ])
      const map: Record<string, GenerationStatusRecord> = {}
      for (const item of res.items) {
        map[item.item] = item
      }
      map.overview = {
        item: "overview",
        status: profile.exists ? "completed" : "pending",
        created_at: null,
        updated_at: null,
        error: null,
      }
      setStatuses(map)
    } catch (err) {
      console.error("Failed to fetch generation status", err)
      toast.error(t("generation.fetchFailed"))
    } finally {
      setInitialLoading(false)
    }
  }

  const handleGenerate = async () => {
    if (selected.length === 0 || !projectId) return
    setLoading(true)
    try {
      // "overview" triggers both machine summary (via scheduler) and PROJECT.md
      const mappedItems = selected.flatMap((i) =>
        i === "overview" ? ["summary", "overview"] : [i],
      )
      const schedulerItems = mappedItems.filter((i) => SCHEDULER_ITEMS.has(i))
      const profileSelected = mappedItems.includes("overview")

      if (schedulerItems.length > 0) {
        await ProjectsService.dispatchGenerationEndpoint({
          projectId: Number(projectId),
          requestBody: {
            project_id: Number(projectId),
            items: schedulerItems,
          },
        })
      }

      if (profileSelected) {
        await ProjectProfilesService.projectsDiscoverProfile({
          projectId: Number(projectId),
          requestBody: { project_id: Number(projectId), record_secrets: false },
        })
        setStatuses((prev) => ({
          ...prev,
          overview: {
            ...prev.overview,
            item: "overview",
            status: "running",
          },
        }))
      }

      toast.success(t("generation.dispatched"))
      setSelected([])
      await fetchStatus()
    } catch (err) {
      console.error("Failed to dispatch generation", err)
      toast.error(t("generation.dispatchFailed"))
    } finally {
      setLoading(false)
    }
  }

  const handleRetry = async (item: string) => {
    if (!projectId) return
    try {
      if (item === "overview") {
        await ProjectProfilesService.projectsDiscoverProfile({
          projectId: Number(projectId),
          requestBody: { project_id: Number(projectId), record_secrets: false },
        })
        setStatuses((prev) => ({
          ...prev,
          overview: {
            ...prev.overview,
            item: "overview",
            status: "running",
          },
        }))
      } else {
        await ProjectsService.retryGenerationEndpoint({
          projectId: Number(projectId),
          item,
          requestBody: {
            project_id: Number(projectId),
            item,
          },
        })
      }
      toast.success(t("generation.retried", { item }))
      await fetchStatus()
    } catch (err) {
      console.error("Failed to retry generation", err)
      toast.error(t("generation.retryFailed"))
    }
  }

  useEffect(() => {
    fetchStatus()
  }, [projectId])

  useEffect(() => {
    const hasRunning = Object.values(statuses).some(
      (s) => s.status === "running",
    )
    if (!hasRunning) return
    const interval = setInterval(() => {
      fetchStatus()
    }, 5000)
    return () => clearInterval(interval)
  }, [statuses])

  useEffect(() => {
    if (!projectId) return
    const pid = Number(projectId)
    const handler = (event: any) => {
      const data = event?.data
      if (data?.project_id === pid) {
        fetchStatus()
      }
    }
    systemSSEClient.on("generation.status", handler)
    return () => systemSSEClient.off("generation.status", handler)
  }, [projectId])

  if (initialLoading) {
    return (
      <div className="flex items-center justify-center h-40">
        <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
      </div>
    )
  }

  return (
    <div className="space-y-6 p-6">
      <Card>
        <CardHeader>
          <CardTitle>{t("generation.title")}</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <p className="text-muted-foreground">{t("generation.description")}</p>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            {ARTIFACTS.map((artifact) => {
              const status = statuses[artifact.key]
              const checked = selected.includes(artifact.key)
              const disabled = status?.status === "running" || loading
              const completed = status?.status === "completed"
              return (
                <div
                  key={artifact.key}
                  className="flex items-center justify-between border rounded-lg p-4"
                >
                  <div className="flex items-center gap-3">
                    <Checkbox
                      id={artifact.key}
                      checked={checked}
                      disabled={disabled}
                      onCheckedChange={(checkedValue) => {
                        setSelected((prev) =>
                          checkedValue
                            ? [...prev, artifact.key]
                            : prev.filter((k) => k !== artifact.key),
                        )
                      }}
                    />
                    <label
                      htmlFor={artifact.key}
                      className="text-sm font-medium"
                    >
                      {t(artifact.labelKey)}
                    </label>
                  </div>
                  <div className="flex items-center gap-2">
                    {status && <GenerationStatusBadge status={status.status} />}
                    {completed && (
                      <Link
                        to={`/projects/$projectId/${artifact.route}` as any}
                        params={{ projectId: projectId! } as any}
                      >
                        <Button
                          variant="ghost"
                          size="icon"
                          title={t("common.preview")}
                        >
                          <Eye className="h-4 w-4" />
                        </Button>
                      </Link>
                    )}
                    {status?.status === "failed" && (
                      <Button
                        variant="ghost"
                        size="icon"
                        onClick={() => handleRetry(artifact.key)}
                        title={t("generation.retry")}
                      >
                        <RefreshCw className="h-4 w-4" />
                      </Button>
                    )}
                  </div>
                </div>
              )
            })}
          </div>
          <Button
            onClick={handleGenerate}
            disabled={selected.length === 0 || loading}
            className="w-full sm:w-auto"
          >
            {loading ? (
              <Loader2 className="h-4 w-4 mr-2 animate-spin" />
            ) : (
              <Play className="h-4 w-4 mr-2" />
            )}
            {t("generation.generate")}
          </Button>
        </CardContent>
      </Card>
      <GenerationHistoryList statuses={statuses} onRetry={handleRetry} />
    </div>
  )
}
