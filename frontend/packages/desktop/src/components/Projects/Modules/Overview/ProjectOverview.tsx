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
  Activity,
  BookOpen,
  CheckCircle2,
  CheckSquare,
  Clock,
  FileText,
  ListTodo,
  RefreshCw,
  Rocket,
  Users,
} from "lucide-react"
import type React from "react"
import { useEffect, useState } from "react"
import { useTranslation } from "react-i18next"
import { toast } from "sonner"
import {
  ProjectModulesService,
  ProjectProfilesService,
  TasksService,
  WikiService,
} from "@/client/sdk.gen"
import { useProjectStore } from "@/stores/projectStore"
import { DiscoverDialog } from "./DiscoverDialog"

// import { Avatar, AvatarFallback, AvatarImage } from "@shared/components/ui/avatar"

interface ProjectStats {
  total_tasks: number
  completed_tasks: number
  active_tasks: number
  pending_tasks: number
  members_count: number
}

interface RecentTask {
  task_id: number
  task_title: string
  status: number
  priority: number
  update_time_format: string
}

export const ProjectOverview: React.FC = () => {
  const { projectId } = useParams({ from: "/_layout/projects/$projectId" })
  const { currentProject } = useProjectStore()
  const { t } = useTranslation()
  const [stats, setStats] = useState<ProjectStats | null>(null)
  // const [members, setMembers] = useState<ProjectMember[]>([])
  const [recentTasks, setRecentTasks] = useState<RecentTask[]>([])
  const [loading, setLoading] = useState(true)
  const [discoverOpen, setDiscoverOpen] = useState(false)
  const [hasProfile, setHasProfile] = useState(false)
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

        // Fetch tasks for recent activity
        const tasksData = (await TasksService.getProjectTasks({
          projectId: parseInt(projectId, 10),
          page: 1,
          pageSize: 5, // Top 5 recent
          status: 1, // Pending
        })) as any
        if (tasksData.code === 0) {
          setRecentTasks(tasksData.data.list || [])
        }

        // Check if profile exists
        const profileData = await ProjectProfilesService.getProfile({
          projectId: parseInt(projectId, 10),
        })
        setHasProfile(profileData.exists === true)

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
      <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">
              {t("projects.stats.totalTasks")}
            </CardTitle>
            <Activity className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">{stats?.total_tasks || 0}</div>
          </CardContent>
        </Card>
        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">
              {t("projects.stats.completed")}
            </CardTitle>
            <CheckCircle2 className="h-4 w-4 text-green-500" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">
              {stats?.completed_tasks || 0}
            </div>
          </CardContent>
        </Card>
        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">
              {t("projects.stats.inProgress")}
            </CardTitle>
            <Clock className="h-4 w-4 text-blue-500" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">{stats?.active_tasks || 0}</div>
          </CardContent>
        </Card>
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

      <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-7">
        {/* Recent Activity */}
        <Card className="col-span-4">
          <CardHeader>
            <CardTitle>{t("projects.overview.recentActivity")}</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="space-y-4">
              {recentTasks.length === 0 ? (
                <div className="text-center text-sm text-muted-foreground py-4">
                  {t("projects.overview.noActivity")}
                </div>
              ) : (
                recentTasks.map((task) => (
                  <div
                    key={task.task_id}
                    className="flex items-center justify-between border-b last:border-0 pb-2 last:pb-0"
                  >
                    <div className="space-y-1">
                      <p className="text-sm font-medium leading-none">
                        {task.task_title}
                      </p>
                      <p className="text-xs text-muted-foreground">
                        {task.update_time_format}
                      </p>
                    </div>
                    <div className="flex items-center gap-2">
                      <Badge
                        variant={task.status === 2 ? "default" : "secondary"}
                      >
                        {task.status === 2
                          ? t("projects.tasks.statusLabel.inProgress")
                          : task.status === 3
                            ? t("projects.tasks.statusLabel.completed")
                            : t("projects.tasks.statusLabel.pending")}
                      </Badge>
                    </div>
                  </div>
                ))
              )}
            </div>
          </CardContent>
        </Card>

        {/* Quick Actions / Members */}
        <Card className="col-span-3">
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
            <Link
              to="/projects/$projectId/tasks"
              params={{ projectId: projectId! }}
              className="block"
            >
              <Button variant="outline" className="w-full justify-start">
                <CheckSquare className="mr-2 h-4 w-4" />
                {t("projects.actions.viewTasks")}
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
