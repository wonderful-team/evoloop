import { Badge } from "@evoloop/shared/components/ui/badge"
import { Button } from "@evoloop/shared/components/ui/button"
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@evoloop/shared/components/ui/card"
import { Link, useParams } from "@tanstack/react-router"
import {
  FileText,
  Loader2,
  Zap,
  ExternalLink,
  RotateCcw,
  Sparkles,
  ChevronDown,
  ChevronRight,
} from "lucide-react"
import { useEffect, useState } from "react"
import { useTranslation } from "react-i18next"
import { toast } from "sonner"
import { ProjectsService } from "@/client"
import { ProjectProfilesService } from "@/client/sdk.gen"
import { MarkdownRenderer } from "@/components/Common/MarkdownRenderer"
import { systemSSEClient } from "@/lib/SystemSSEClient"

interface SummaryData {
  description: string
  technical_stack: string[]
  core_features: string[]
}

export function GenerationPanel() {
  const { projectId } = useParams({ from: "/_layout/projects/$projectId" })
  const { t } = useTranslation()
  const [statuses, setStatuses] = useState<Record<string, any>>({})
  const [generating, setGenerating] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)
  const [summary, setSummary] = useState<SummaryData | null>(null)
  const [profileContent, setProfileContent] = useState<string | null>(null)
  const [overviewOpen, setOverviewOpen] = useState(true)

  const fetchStatus = async () => {
    if (!projectId) return
    try {
      const [res, profile] = await Promise.all([
        ProjectsService.listGenerationStatusEndpoint({ projectId: Number(projectId) }),
        ProjectProfilesService.projectsGetProfile({ projectId: Number(projectId) }),
      ])
      const map: Record<string, any> = {}
      for (const item of res.items) map[item.item] = item
      map.overview = { item: "overview", status: profile.exists ? "completed" : "pending" }
      setStatuses(map)

      if (profile.exists) {
        setProfileContent(profile.content ?? null)
        const summaryRes = await ProjectsService.getGenerationContentEndpoint({
          projectId: Number(projectId), item: "summary",
        }).catch(() => ({ content: null }))
        if (summaryRes?.content) {
          try { setSummary(JSON.parse(summaryRes.content)) } catch { setSummary(null) }
        }
      }
    } catch { /* ignore */
    } finally { setLoading(false) }
  }

  const generate = async (key: string) => {
    if (!projectId) return
    setGenerating(key)
    try {
      if (key === "overview") {
        await Promise.all([
          ProjectsService.dispatchGenerationEndpoint({
            projectId: Number(projectId), requestBody: { project_id: Number(projectId), items: ["summary"] },
          }),
          ProjectProfilesService.projectsDiscoverProfile({
            projectId: Number(projectId), requestBody: { project_id: Number(projectId), record_secrets: false },
          }),
        ])
      } else {
        await ProjectsService.dispatchGenerationEndpoint({
          projectId: Number(projectId), requestBody: { project_id: Number(projectId), items: [key] },
        })
      }
      setStatuses((prev) => ({ ...prev, [key]: { ...prev[key], status: "running" } }))
      toast.success(t("generation.dispatched"))
    } catch { toast.error(t("generation.dispatchFailed"))
    } finally { setGenerating(null) }
  }

  const retry = async (key: string) => {
    if (!projectId) return
    setGenerating(key)
    try {
      if (key === "overview") {
        await ProjectProfilesService.projectsDiscoverProfile({
          projectId: Number(projectId), requestBody: { project_id: Number(projectId), record_secrets: false },
        })
      } else {
        await ProjectsService.retryGenerationEndpoint({
          projectId: Number(projectId), item: key,
          requestBody: { project_id: Number(projectId), item: key },
        })
      }
      setStatuses((prev) => ({ ...prev, [key]: { ...prev[key], status: "running" } }))
      toast.success(t("generation.retried", { item: key }))
    } catch { toast.error(t("generation.retryFailed"))
    } finally { setGenerating(null) }
  }

  useEffect(() => { fetchStatus() }, [projectId])

  useEffect(() => {
    const hasRunning = Object.values(statuses).some((s: any) => s.status === "running")
    if (!hasRunning) return
    const i = setInterval(fetchStatus, 5000)
    return () => clearInterval(i)
  }, [statuses])

  useEffect(() => {
    if (!projectId) return
    const h = (e: any) => { if (e?.data?.project_id === Number(projectId)) fetchStatus() }
    systemSSEClient.on("generation.status", h)
    return () => systemSSEClient.off("generation.status", h)
  }, [projectId])

  if (loading) {
    return (
      <div className="flex items-center justify-center h-48">
        <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
      </div>
    )
  }

  const status = (key: string) => statuses[key]?.status || "pending"

  const ArtifactCard = ({ key: k, icon: Icon, label, route }: { key: string; icon: any; label: string; route: string }) => {
    const st = status(k)
    const busy = generating === k || st === "running"

    const targetRoute =
      route.includes("macros") || route.includes("tasks")
        ? "/projects/$projectId/workflows"
        : "/projects/$projectId/knowledge"

    return (
      <Card className={`transition-all hover:border-primary/40 ${busy ? "border-primary/50 shadow-sm" : ""}`}>
        <CardHeader className="pb-3 flex flex-row items-center justify-between space-y-0">
          <div className="flex items-center gap-2">
            <Icon className="h-5 w-5 text-muted-foreground" />
            <CardTitle className="text-sm font-semibold">{label}</CardTitle>
          </div>
          <Badge variant={st === "completed" ? "default" : st === "failed" ? "destructive" : "secondary"}>
            {st === "completed" && t("generation.status.completed")}
            {st === "running" && t("generation.status.running")}
            {st === "failed" && t("generation.status.failed")}
            {st === "pending" && t("generation.status.pending")}
          </Badge>
        </CardHeader>
        <CardContent>
          {st === "failed" && statuses[k]?.error && (
            <p className="text-xs text-destructive mb-2 truncate">{statuses[k].error}</p>
          )}
          <div className="flex gap-2">
            {(st === "completed" || st === "failed") && (
              <Button variant="outline" size="sm" asChild>
                <Link to={targetRoute as any} params={{ projectId: projectId! } as any}>
                  <ExternalLink className="h-3.5 w-3.5 mr-1.5" />
                  {st === "completed" ? t("common.preview") : t("common.view")}
                </Link>
              </Button>
            )}
            {st === "failed" && (
              <Button variant="outline" size="sm" onClick={() => retry(k)} disabled={busy}>
                <RotateCcw className="h-3.5 w-3.5 mr-1.5" />
                {t("generation.retry")}
              </Button>
            )}
            {(st === "pending" || st === "failed") && !busy && (
              <Button size="sm" onClick={() => generate(k)}>
                <Sparkles className="h-3.5 w-3.5 mr-1.5" />
                {t("generation.generate")}
              </Button>
            )}
            {busy && (
              <span className="text-sm text-primary inline-flex items-center gap-1.5">
                <Loader2 className="h-3.5 w-3.5 animate-spin" />
                {t("generation.running")}
              </span>
            )}
          </div>
        </CardContent>
      </Card>
    )
  }

  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-xl font-semibold tracking-tight">
          {t("generation.title")}
        </h2>
        <p className="text-sm text-muted-foreground mt-1">
          {t("generation.subtitle")}
        </p>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <ArtifactCard key="wiki" icon={FileText} label={t("generation.artifacts.wiki")} route="/wiki" />
        <ArtifactCard key="appmap" icon={Zap} label={t("generation.artifacts.macros")} route="/macros" />
      </div>

      {statuses.overview?.status === "completed" && (summary || profileContent) ? (
        <Card>
          <button onClick={() => setOverviewOpen(!overviewOpen)} className="w-full text-left">
            <CardHeader className="pb-3">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <FileText className="h-5 w-5 text-muted-foreground" />
                  <CardTitle className="text-sm font-semibold">{t("generation.artifacts.overview")}</CardTitle>
                  <CardDescription className="hidden sm:inline">
                    {summary?.technical_stack?.slice(0, 3).join(" · ")}
                  </CardDescription>
                </div>
                {overviewOpen ? <ChevronDown className="h-4 w-4" /> : <ChevronRight className="h-4 w-4" />}
              </div>
            </CardHeader>
          </button>
          {overviewOpen && (
            <CardContent className="space-y-4 pt-0">
              {summary && (
                <>
                  <p className="text-sm leading-relaxed text-muted-foreground">{summary.description}</p>
                  {summary.technical_stack?.length > 0 && (
                    <div className="flex flex-wrap gap-1.5">
                      {summary.technical_stack.map((s: string) => (
                        <span key={s} className="text-xs bg-secondary text-secondary-foreground px-2 py-0.5 rounded-md font-medium">{s}</span>
                      ))}
                    </div>
                  )}
                  {summary.core_features?.length > 0 && (
                    <div className="text-sm text-muted-foreground space-y-0.5">
                      {summary.core_features.map((f: string) => (
                        <div key={f} className="flex items-start gap-2">
                          <span className="text-primary mt-1">·</span>
                          <span>{f}</span>
                        </div>
                      ))}
                    </div>
                  )}
                </>
              )}
              {profileContent && (
                <details className="group border-t pt-3">
                  <summary className="text-sm font-medium cursor-pointer text-muted-foreground hover:text-foreground">
                    {t("projects.profile.documentTitle")}
                  </summary>
                  <div className="mt-3 prose prose-sm max-w-none dark:prose-invert">
                    <MarkdownRenderer content={profileContent} />
                  </div>
                </details>
              )}
            </CardContent>
          )}
        </Card>
      ) : (
        <Card>
          <CardHeader className="pb-3">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                <FileText className="h-5 w-5 text-muted-foreground" />
                <CardTitle className="text-sm font-semibold">{t("generation.artifacts.overview")}</CardTitle>
              </div>
              <Badge variant="secondary">{t("generation.status.pending")}</Badge>
            </div>
          </CardHeader>
          <CardContent>
            <div className="flex items-center justify-between">
              <p className="text-sm text-muted-foreground">{t("generation.notGenerated")}</p>
              <Button size="sm" onClick={() => generate("overview")} disabled={generating === "overview"}>
                {generating === "overview" ? (
                  <Loader2 className="h-3.5 w-3.5 mr-1.5 animate-spin" />
                ) : <Sparkles className="h-3.5 w-3.5 mr-1.5" />}
                {t("generation.generate")}
              </Button>
            </div>
          </CardContent>
        </Card>
      )}
    </div>
  )
}
