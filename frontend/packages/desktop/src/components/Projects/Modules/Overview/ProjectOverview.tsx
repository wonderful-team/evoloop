import { Badge } from "@evoloop/shared/components/ui/badge"
import { Button } from "@evoloop/shared/components/ui/button"
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
} from "@evoloop/shared/components/ui/card"
import { useMutation, useQueryClient } from "@tanstack/react-query"
import { Link, useParams } from "@tanstack/react-router"
import {
  BookOpen,
  FileText,
  ListTodo,
  RefreshCw,
  Rocket,
  Sparkles,
  Users,
} from "lucide-react"
import type React from "react"
import { useEffect, useState } from "react"
import { useTranslation } from "react-i18next"
import { toast } from "sonner"
import {
  ProjectModulesService,
  ProjectProfilesService,
  ProjectsService,
  WikiService,
} from "@/client/sdk.gen"
import { useProjectStore } from "@/stores/projectStore"
import { DiscoverDialog } from "./DiscoverDialog"

// import { Avatar, AvatarFallback, AvatarImage } from "@shared/components/ui/avatar"

interface ProjectStats {
  members_count: number
}

export const ProjectOverview: React.FC = () => {
  const { projectId } = useParams({ from: "/_layout/projects/$projectId" })
  const { currentProject } = useProjectStore()
  const { t } = useTranslation()
  const [stats, setStats] = useState<ProjectStats | null>(null)
  // const [members, setMembers] = useState<ProjectMember[]>([])
  const [loading, setLoading] = useState(true)
  const [discoverOpen, setDiscoverOpen] = useState(false)
  const [hasProfile, setHasProfile] = useState(false)
  const [generationItems, setGenerationItems] = useState<Array<{ item: string; status: string }>>([])
  const queryClient = useQueryClient()

  const { mutate: handleGenerateWiki, isPending: isWikiPending } = useMutation({
    mutationFn: async () => {
      return WikiService.generateWiki({
        requestBody: {
          project_id: Number(projectId),
          topic: t("wiki.topic.full_documentation"),
          force_regenerate: true,
        },
      })
    },
    onSuccess: () => {
      toast.success(t("wiki.toast.start"))
      queryClient.invalidateQueries({ queryKey: ["wiki"] })
    },
    onError: (_error: any) => {
      toast.error(t("wiki.toast.error"))
    },
  })

  useEffect(() => {
    const loadData = async () => {
      if (!projectId) return
      setLoading(true)
      try {
        // Backend identifies user via Cookie Session.
        const statsData = (await ProjectModulesService.getProjectStatistics({
          projectId: parseInt(projectId, 10),
        })) as any
        if (statsData.code === 0) {
          setStats(statsData.data)
        }

        // Check if profile exists
        const profileData = await ProjectProfilesService.projectsGetProfile({
          projectId: parseInt(projectId, 10),
        })
        setHasProfile(profileData.exists === true)

        // Fetch generation artifacts status
        try {
          const genData = await ProjectsService.listGenerationStatusEndpoint({
            projectId: Number(projectId),
          })
          setGenerationItems(
            (genData.items ?? []).filter(
              (g: any) => g.status === "completed" || g.status === "failed" || g.status === "running",
            ),
          )
        } catch {
          // Generation endpoints may not be available; silently skip
        }

        // Fetch Project Detail for members (using ProjectModulesService or ProjectsService?)
        // Assuming we can get members from project detail or stats
        // For now, let's look at what we have.
        // The mobile app gets members from project detail.
        // Let's defer members fetching or try to use a service if available.
        // We'll leave members empty for now if not easily available, or check ProjectsService
      } catch (error) {
        console.error("Failed to load overview data", error)
      } finally {
        setLoading(false)
      }
    }
    loadData()
  }, [projectId])

  if (loading) {
    return <div className="p-6">{t("common.loading")}</div>
  }

  return (
    <div className="h-full w-full overflow-auto p-6 space-y-6">
      <div className="flex justify-between items-center">
        <div className="flex items-center gap-3">
          <h2 className="text-2xl font-bold tracking-tight">
            {t("projects.overview.title")}
          </h2>
          {/* Status Badges */}
          {currentProject?.indexing_status === "indexing" && (
            <Badge
              variant="secondary"
              className="bg-blue-100 text-blue-700 gap-1"
            >
              <RefreshCw className="h-3.5 w-3.5 animate-spin" />{" "}
              {t("projects.status.indexing")}
            </Badge>
          )}
          {(currentProject?.summarization_status === "running" ||
            currentProject?.summarization_status === "summarizing") && (
            <Badge
              variant="secondary"
              className="bg-purple-100 text-purple-700 gap-1"
            >
              <ListTodo className="h-3.5 w-3.5 animate-pulse" />{" "}
              {t("projects.status.analyzing")}
            </Badge>
          )}
        </div>
      </div>

      {/* Stats Grid */}
      <div className="grid gap-4 md:grid-cols-2">
        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">
              {t("projects.stats.members")}
            </CardTitle>
            <Users className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">
              {stats?.members_count || 0}
            </div>
          </CardContent>
        </Card>
      </div>

      {/* Recent Generation Artifacts */}
      {generationItems.length > 0 && (
        <Card>
          <CardHeader className="flex flex-row items-center justify-between">
            <CardTitle className="text-sm font-medium flex items-center gap-2">
              <Sparkles className="h-4 w-4 text-primary" />
              {t("generation.title")}
            </CardTitle>
            <Link
              to="/projects/$projectId/generation"
              params={{ projectId: projectId! }}
            >
              <Button variant="ghost" size="sm">
                {t("common.preview")}
              </Button>
            </Link>
          </CardHeader>
          <CardContent>
            <div className="flex flex-wrap gap-2">
              {generationItems.map((g) => (
                <Link
                  key={g.item}
                  to={`/projects/$projectId/${g.item === "overview" ? "overview" : g.item}` as any}
                  params={{ projectId: projectId! } as any}
                >
                  <Badge
                    variant={
                      g.status === "completed"
                        ? "secondary"
                        : g.status === "running"
                          ? "default"
                          : "destructive"
                    }
                    className="cursor-pointer"
                  >
                    {t(`generation.artifacts.${g.item}`, {defaultValue: g.item})}
                  </Badge>
                </Link>
              ))}
            </div>
          </CardContent>
        </Card>
      )}

      <div className="grid gap-4 md:grid-cols-1">
        {/* Quick Actions / Members */}
        <Card>
          <CardHeader>
            <CardTitle>{t("projects.overview.quickActions")}</CardTitle>
          </CardHeader>
          <CardContent className="space-y-2">
            <Button
              variant="outline"
              className="w-full justify-start hover:bg-primary/5 hover:text-primary transition-all border-dashed"
              onClick={() => setDiscoverOpen(true)}
            >
              {hasProfile ? (
                <RefreshCw className="mr-2 h-4 w-4 text-blue-500" />
              ) : (
                <Rocket className="mr-2 h-4 w-4 text-primary" />
              )}
              {t("chat.sidebar.deploy")}
            </Button>
            <Button
              variant="outline"
              className="w-full justify-start hover:bg-primary/5 hover:text-primary transition-all"
              onClick={() => handleGenerateWiki()}
              disabled={isWikiPending}
            >
              <BookOpen className="mr-2 h-4 w-4 text-green-500" />
              {currentProject?.has_wiki
                ? t("wiki.regenerate_action")
                : t("wiki.generate")}
            </Button>
            <Link
              to="/projects/$projectId/profile"
              params={{ projectId: projectId! }}
              className="block"
            >
              <Button variant="outline" className="w-full justify-start">
                <FileText className="mr-2 h-4 w-4" />
                {t("projects.tabs.profile")}
              </Button>
            </Link>
          </CardContent>
        </Card>

        <DiscoverDialog
          projectId={parseInt(projectId || "0", 10)}
          open={discoverOpen}
          onOpenChange={setDiscoverOpen}
          onDiscovered={() => setHasProfile(true)}
        />
      </div>
    </div>
  )
}
