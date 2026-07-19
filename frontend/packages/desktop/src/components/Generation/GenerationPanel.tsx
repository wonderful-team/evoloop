import { Button } from "@evoloop/shared/components/ui/button"
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
} from "@evoloop/shared/components/ui/card"
import { Link, useParams } from "@tanstack/react-router"
import {
  FileText,
  Loader2,
  Play,
  RefreshCw,
  Zap,
  ExternalLink,
  CheckCircle2,
  Clock,
  AlertCircle,
} from "lucide-react"
import { useEffect, useState } from "react"
import { useTranslation } from "react-i18next"
import { toast } from "sonner"
import { type GenerationStatusRecord, ProjectsService } from "@/client"
import { ProjectProfilesService } from "@/client/sdk.gen"
import { MarkdownRenderer } from "@/components/Common/MarkdownRenderer"
import { systemSSEClient } from "@/lib/SystemSSEClient"

interface ArtifactDef {
  key: string
  labelKey: string
  icon: typeof FileText
  route: string
}

const ARTIFACTS: ArtifactDef[] = [
  { key: "wiki", labelKey: "generation.artifacts.wiki", icon: FileText, route: "/wiki" },
  { key: "appmap", labelKey: "generation.artifacts.macros", icon: Zap, route: "/macros" },
]

export function GenerationPanel() {
  const { projectId } = useParams({ from: "/_layout/projects/$projectId" })
  const { t } = useTranslation()
  const [statuses, setStatuses] = useState<Record<string, GenerationStatusRecord>>({})
  const [generating, setGenerating] = useState<string | null>(null)
  const [initialLoading, setInitialLoading] = useState(true)
  const [summaryData, setSummaryData] = useState<any>(null)
  const [profileContent, setProfileContent] = useState<string | null>(null)

  const fetchStatus = async () => {
    if (!projectId) return
    try {
      const [res, profile] = await Promise.all([
        ProjectsService.listGenerationStatusEndpoint({ projectId: Number(projectId) }),
        ProjectProfilesService.projectsGetProfile({ projectId: Number(projectId) }),
      ])
      const map: Record<string, GenerationStatusRecord> = {}
      for (const item of res.items) map[item.item] = item
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

  const handleGenerate = async (key: string) => {
    if (!projectId) return
    setGenerating(key)
    try {
      if (key === "overview") {
        await ProjectsService.dispatchGenerationEndpoint({
          projectId: Number(projectId),
          requestBody: { project_id: Number(projectId), items: ["summary"] },
        })
        await ProjectProfilesService.projectsDiscoverProfile({
          projectId: Number(projectId),
          requestBody: { project_id: Number(projectId), record_secrets: false },
        })
      } else {
        await ProjectsService.dispatchGenerationEndpoint({
          projectId: Number(projectId),
          requestBody: { project_id: Number(projectId), items: [key] },
        })
      }
      setStatuses((prev) => ({
        ...prev,
        [key]: { ...prev[key], item: key, status: "running" },
      }))
      toast.success(t("generation.dispatched"))
    } catch (err) {
      console.error("Failed to dispatch", err)
      toast.error(t("generation.dispatchFailed"))
    } finally {
      setGenerating(null)
    }
  }

  const handleRetry = async (key: string) => {
    if (!projectId) return
    setGenerating(key)
    try {
      if (key === "overview") {
        await ProjectProfilesService.projectsDiscoverProfile({
          projectId: Number(projectId),
          requestBody: { project_id: Number(projectId), record_secrets: false },
        })
      } else {
        await ProjectsService.retryGenerationEndpoint({
          projectId: Number(projectId),
          item: key,
          requestBody: { project_id: Number(projectId), item: key },
        })
      }
      setStatuses((prev) => ({
        ...prev,
        [key]: { ...prev[key], status: "running" },
      }))
      toast.success(t("generation.retried", { item: key }))
    } catch (err) {
      console.error("Failed to retry", err)
      toast.error(t("generation.retryFailed"))
    } finally {
      setGenerating(null)
    }
  }

  useEffect(() => { fetchStatus() }, [projectId])

  useEffect(() => {
    if (statuses.overview?.status !== "completed") return
    const load = async () => {
      try {
        const [profileRes, summaryRes] = await Promise.all([
          ProjectProfilesService.projectsGetProfile({ projectId: Number(projectId) }),
          ProjectsService.getGenerationContentEndpoint({
            projectId: Number(projectId), item: "summary",
          }).catch(() => ({ content: null })),
        ])
        setProfileContent(profileRes.content ?? null)
        if (summaryRes?.content) {
          try { setSummaryData(JSON.parse(summaryRes.content)) } catch { setSummaryData(null) }
        }
      } catch { /* ignore */ }
    }
    load()
  }, [statuses.overview?.status, projectId])

  useEffect(() => {
    const hasRunning = Object.values(statuses).some((s) => s.status === "running")
    if (!hasRunning) return
    const interval = setInterval(fetchStatus, 5000)
    return () => clearInterval(interval)
  }, [statuses])

  useEffect(() => {
    if (!projectId) return
    const pid = Number(projectId)
    const handler = (event: any) => {
      if (event?.data?.project_id === pid) fetchStatus()
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
      <div>
        <h2 className="text-2xl font-bold tracking-tight">{t("generation.title")}</h2>
        <p className="text-muted-foreground mt-1">{t("generation.description")}</p>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        {ARTIFACTS.map((artifact) => {
          const s = statuses[artifact.key]
          const isRunning = s?.status === "running" || generating === artifact.key
          const isCompleted = s?.status === "completed"
          const isFailed = s?.status === "failed"
          const Icon = artifact.icon

          return (
            <Card key={artifact.key} className={`relative ${isRunning ? "border-blue-300" : ""}`}>
              <CardHeader className="pb-3">
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    <Icon className="h-5 w-5 text-muted-foreground" />
                    <CardTitle className="text-base">{t(artifact.labelKey)}</CardTitle>
                  </div>
                  {isCompleted && <CheckCircle2 className="h-5 w-5 text-green-500" />}
                  {isFailed && <AlertCircle className="h-5 w-5 text-red-500" />}
                  {isRunning && <Loader2 className="h-5 w-5 animate-spin text-blue-500" />}
                  {!s && <Clock className="h-5 w-5 text-muted-foreground" />}
                </div>
              </CardHeader>
              <CardContent>
                {isFailed && s?.error && (
                  <p className="text-xs text-red-600 mb-3 truncate">{s.error}</p>
                )}

                <div className="flex gap-2">
                  {(isCompleted || isFailed) && (
                    <Link
                      to={`/projects/$projectId${artifact.route}` as any}
                      params={{ projectId: projectId! } as any}
                    >
                      <Button variant="outline" size="sm">
                        <ExternalLink className="h-3 w-3 mr-1" />
                        {t("common.preview")}
                      </Button>
                    </Link>
                  )}

                  {isFailed && (
                    <Button
                      variant="outline"
                      size="sm"
                      onClick={() => handleRetry(artifact.key)}
                      disabled={isRunning}
                    >
                      <RefreshCw className="h-3 w-3 mr-1" />
                      {t("generation.retry")}
                    </Button>
                  )}

                  {(!s || isFailed) && !isRunning && (
                    <Button
                      size="sm"
                      onClick={() => handleGenerate(artifact.key)}
                    >
                      <Play className="h-3 w-3 mr-1" />
                      {t("generation.generate")}
                    </Button>
                  )}

                  {isRunning && (
                    <span className="text-xs text-blue-600 self-center ml-1">
                      {t("generation.running")}
                    </span>
                  )}
                </div>

                {isCompleted && s?.created_at && (
                  <p className="text-xs text-muted-foreground mt-3">
                    {t("generation.generatedAt", { time: new Date(s.created_at).toLocaleString() })}
                  </p>
                )}
              </CardContent>
            </Card>
          )
        })}
      </div>

      {(summaryData || profileContent || (!statuses.overview)) && (
        <Card>
          <CardHeader>
            <CardTitle className="text-base">{t("generation.artifacts.overview")}</CardTitle>
          </CardHeader>
          <CardContent>
            {!statuses.overview || statuses.overview?.status === "pending" ? (
              <div className="flex items-center justify-between">
                <p className="text-sm text-muted-foreground">
                  {t("generation.notGenerated")}
                </p>
                <Button size="sm" onClick={() => handleGenerate("overview")}
                        disabled={generating === "overview"}>
                  {generating === "overview" ? (
                    <Loader2 className="h-3 w-3 mr-1 animate-spin" />
                  ) : <Play className="h-3 w-3 mr-1" />}
                  {t("generation.generate")}
                </Button>
              </div>
            ) : generating === "overview" ? (
              <div className="flex items-center gap-2 text-sm text-blue-600">
                <Loader2 className="h-4 w-4 animate-spin" />
                {t("generation.running")}
              </div>
            ) : (
              <div className="space-y-4">
                {summaryData && (
                  <>
                    <p className="text-sm">{summaryData.description}</p>
                    {summaryData.technical_stack?.length > 0 && (
                      <div className="flex flex-wrap gap-1">
                        {summaryData.technical_stack.map((s: string) => (
                          <span key={s} className="text-xs bg-secondary text-secondary-foreground px-2 py-0.5 rounded">{s}</span>
                        ))}
                      </div>
                    )}
                  </>
                )}
                {profileContent && (
                  <details className="group">
                    <summary className="text-sm font-medium cursor-pointer text-muted-foreground hover:text-foreground">
                      {t("projects.profile.documentTitle")}
                    </summary>
                    <div className="mt-2 prose prose-sm max-w-none">
                      <MarkdownRenderer content={profileContent} />
                    </div>
                  </details>
                )}
              </div>
            )}
          </CardContent>
        </Card>
      )}

      <Card>
        <CardHeader>
          <CardTitle className="text-sm">{t("generation.history")}</CardTitle>
        </CardHeader>
        <CardContent>
          {Object.entries(statuses).filter(([k]) => k !== "appmap" || k).length === 0 ? (
            <p className="text-sm text-muted-foreground">{t("generation.noHistory")}</p>
          ) : (
            <div className="space-y-1">
              {Object.entries(statuses).map(([key, s]) => (
                <div key={key} className="flex items-center justify-between text-sm py-1">
                  <span>{t(`generation.artifacts.${key}`, key)}</span>
                  <span className="text-muted-foreground">
                    {s.status === "completed" && t("generation.status.completed")}
                    {s.status === "running" && t("generation.status.running")}
                    {s.status === "failed" && t("generation.status.failed")}
                    {s.status === "pending" && t("generation.status.pending")}
                    {!s && t("generation.status.pending")}
                  </span>
                </div>
              ))}
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  )
}
