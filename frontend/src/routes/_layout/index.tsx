import { useQuery } from "@tanstack/react-query"
import { createFileRoute, useNavigate } from "@tanstack/react-router"
import {
  Activity,
  Box,
  CheckCircle2,
  Clock,
  ExternalLink,
  HardDrive,
  Plus,
  Server,
  Terminal,
} from "lucide-react"
import { useTranslation } from "react-i18next"
// Services via SDK
import {
  McpService,
  ProjectModulesService,
  ProjectsService,
  UtilsService,
} from "@/client/sdk.gen"
// UI Components
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import {
  Card,
  CardContent,
  CardDescription,
  CardFooter,
  CardHeader,
  CardTitle,
} from "@/components/ui/card"
import { ScrollArea } from "@/components/ui/scroll-area"
import { Separator } from "@/components/ui/separator"
import { Skeleton } from "@/components/ui/skeleton"
import useAuth from "@/hooks/useAuth"

export const Route = createFileRoute("/_layout/")({
  component: Dashboard,
  head: () => ({
    meta: [
      {
        title: "Dashboard - EvoLoop",
      },
    ],
  }),
})

function Dashboard() {
  const { t } = useTranslation()
  const { user: currentUser } = useAuth()
  const navigate = useNavigate()

  // 1. Fetch Global Statistics
  const { data: stats, isLoading: isStatsLoading } = useQuery({
    queryKey: ["global-stats"],
    queryFn: () => ProjectModulesService.getProjectStatistics({}),
    retry: 1,
  })

  // 2. Fetch Projects
  const { data: projectsData, isLoading: isProjectsLoading } = useQuery({
    queryKey: ["projects"],
    queryFn: () => ProjectsService.getProjects(),
  })
  // Cast to any because generated type is unknown
  const projects = (projectsData as any)?.projects || []

  // 3. Fetch MCP Servers
  const { data: mcpServers, isLoading: isMcpLoading } = useQuery({
    queryKey: ["mcp-servers"],
    queryFn: () => McpService.listMcpServers(),
  })

  // 4. System Status
  const { data: systemStatus } = useQuery({
    queryKey: ["system-status"],
    queryFn: () => UtilsService.getEvoloopStatus(),
  })

  // Helpers
  const greeting = () => {
    const hour = new Date().getHours()
    if (hour < 12) return t("dashboard.greeting.morning")
    if (hour < 18) return t("dashboard.greeting.afternoon")
    return t("dashboard.greeting.evening")
  }

  return (
    <div className="flex flex-col gap-6 p-6">
      {/* Header Section */}
      <div className="flex flex-col md:flex-row justify-between items-start md:items-center gap-4">
        <div>
          <h1 className="text-3xl font-bold tracking-tight">
            {greeting()},{" "}
            {currentUser?.nickname ||
              currentUser?.username ||
              t("user.defaultName")}
          </h1>
          <p className="text-muted-foreground mt-1">
            {t("dashboard.greeting.welcome")}
          </p>
        </div>
        <div className="flex items-center gap-2">
          <Button onClick={() => navigate({ to: "/projects" })}>
            <Plus className="mr-2 h-4 w-4" /> {t("dashboard.projects.create")}
          </Button>
        </div>
      </div>

      <Separator />

      {/* KPI Stats Cards */}
      <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
        <StatsCard
          title={t("dashboard.stats.activeProjects")}
          value={
            isProjectsLoading
              ? null
              : projects.filter((p: any) => p.exists_locally).length.toString()
          }
          icon={<Box className="h-4 w-4 text-muted-foreground" />}
          description={t("dashboard.stats.activeProjectsDesc")}
        />
        <StatsCard
          title={t("dashboard.stats.totalTasks")}
          value={
            isStatsLoading
              ? null
              : ((stats as any)?.total_tasks || 0).toString()
          }
          icon={<CheckCircle2 className="h-4 w-4 text-muted-foreground" />}
          description={t("dashboard.stats.totalTasksDesc")}
        />
        <StatsCard
          title={t("dashboard.stats.pendingTasks")}
          value={
            isStatsLoading
              ? null
              : ((stats as any)?.pending_tasks || 0).toString()
          }
          icon={<Clock className="h-4 w-4 text-muted-foreground" />}
          description={t("dashboard.stats.pendingTasksDesc")}
        />
        <StatsCard
          title={t("dashboard.stats.systemServices")}
          value={
            isMcpLoading ? null : ((mcpServers as any)?.length || 0).toString()
          }
          icon={<Server className="h-4 w-4 text-muted-foreground" />}
          description={t("dashboard.stats.systemServicesDesc")}
        />
      </div>

      <div className="grid gap-6 md:grid-cols-7 lg:grid-cols-8">
        {/* Main Content: Projects Grid (Col Span 5 or 6) */}
        <div className="md:col-span-4 lg:col-span-5 flex flex-col gap-6">
          <div className="flex items-center justify-between">
            <h2 className="text-xl font-semibold tracking-tight">
              {t("dashboard.projects.recent")}
            </h2>
            <Button
              variant="link"
              className="px-0"
              onClick={() => navigate({ to: "/projects" })}
            >
              {t("dashboard.projects.viewAll")}
            </Button>
          </div>

          {isProjectsLoading ? (
            <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
              {[1, 2, 3].map((i) => (
                <Skeleton key={i} className="h-[180px] w-full rounded-xl" />
              ))}
            </div>
          ) : projects.length === 0 ? (
            <div className="flex flex-col items-center justify-center p-8 border border-dashed rounded-xl bg-muted/50">
              <div className="h-12 w-12 rounded-full bg-background flex items-center justify-center mb-4">
                <Box className="h-6 w-6 text-muted-foreground" />
              </div>
              <h3 className="text-lg font-medium">
                {t("dashboard.projects.noProjects")}
              </h3>
              <p className="text-muted-foreground text-center max-w-sm mt-2 mb-4">
                {t("dashboard.projects.noProjectsDesc")}
              </p>
              <Button onClick={() => navigate({ to: "/projects" })}>
                {t("dashboard.projects.create")}
              </Button>
            </div>
          ) : (
            <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
              {projects.slice(0, 6).map((project: any) => (
                <ProjectCard
                  key={project.id}
                  project={project}
                  navigate={navigate}
                  t={t}
                />
              ))}
            </div>
          )}
        </div>

        {/* Sidebar: System Status & MCP (Col Span 2 or 3) */}
        <div className="md:col-span-3 lg:col-span-3 flex flex-col gap-6">
          {/* MCP Servers Widget */}
          <Card className="h-full max-h-[500px] flex flex-col">
            <CardHeader>
              <CardTitle className="flex items-center justify-between text-lg">
                <span>{t("dashboard.ecosystem.title")}</span>
                <Server className="h-4 w-4 text-muted-foreground" />
              </CardTitle>
              <CardDescription>
                {t("dashboard.ecosystem.subtitle")}
              </CardDescription>
            </CardHeader>
            <CardContent className="flex-1 overflow-hidden p-0">
              <ScrollArea className="h-full px-6 pb-4">
                <div className="space-y-4">
                  {isMcpLoading ? (
                    [1, 2].map((i) => (
                      <Skeleton key={i} className="h-12 w-full" />
                    ))
                  ) : !(mcpServers as any) ||
                    (mcpServers as any).length === 0 ? (
                    <div className="text-sm text-muted-foreground py-4 text-center">
                      {t("dashboard.ecosystem.noServers")}
                    </div>
                  ) : (
                    (mcpServers as any).map((server: any) => (
                      <div
                        key={server.name}
                        className="flex items-center justify-between space-x-4 border p-3 rounded-lg bg-card/50"
                      >
                        <div className="flex items-center space-x-3">
                          <div className="p-2 bg-primary/10 rounded-md">
                            <Terminal className="h-4 w-4 text-primary" />
                          </div>
                          <div>
                            <p className="text-sm font-medium leading-none">
                              {server.name}
                            </p>
                            <p className="text-xs text-muted-foreground mt-1">
                              {t("dashboard.ecosystem.toolsAvailable", {
                                count: server.tools_count || 0,
                              })}
                            </p>
                          </div>
                        </div>
                        <Badge
                          variant={
                            server.status === "connected"
                              ? "default"
                              : "secondary"
                          }
                          className="text-[10px] h-5"
                        >
                          {server.status || t("dashboard.ecosystem.active")}
                        </Badge>
                      </div>
                    ))
                  )}

                  {/* System Internal Status (Mocked or from Utils) */}
                  <div
                    key="core-system"
                    className="flex items-center justify-between space-x-4 border p-3 rounded-lg bg-muted/30"
                  >
                    <div className="flex items-center space-x-3">
                      <div className="p-2 bg-green-500/10 rounded-md">
                        <Activity className="h-4 w-4 text-green-600" />
                      </div>
                      <div>
                        <p className="text-sm font-medium leading-none">
                          {t("dashboard.ecosystem.coreAgent")}
                        </p>
                        <p className="text-xs text-muted-foreground mt-1">
                          {t("dashboard.ecosystem.evaluationLoop")}
                        </p>
                      </div>
                    </div>
                    <Badge
                      variant="outline"
                      className="text-[10px] h-5 border-green-500/50 text-green-600"
                    >
                      {(systemStatus as any)?.status
                        ? t("dashboard.ecosystem.online")
                        : t("dashboard.ecosystem.active")}
                    </Badge>
                  </div>
                </div>
              </ScrollArea>
            </CardContent>
            <CardFooter className="bg-muted/20 border-t px-6 py-3">
              <Button
                variant="ghost"
                size="sm"
                className="w-full text-xs text-muted-foreground h-8"
                onClick={() => navigate({ to: "/mcp" })}
              >
                {t("dashboard.ecosystem.manage")}
              </Button>
            </CardFooter>
          </Card>
        </div>
      </div>
    </div>
  )
}

function StatsCard({
  title,
  value,
  icon,
  description,
}: {
  title: string
  value: string | null
  icon: any
  description: string
}) {
  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
        <CardTitle className="text-sm font-medium">{title}</CardTitle>
        {icon}
      </CardHeader>
      <CardContent>
        {value === null ? (
          <Skeleton className="h-8 w-16 mb-1" />
        ) : (
          <div className="text-2xl font-bold">{value}</div>
        )}
        <p className="text-xs text-muted-foreground">{description}</p>
      </CardContent>
    </Card>
  )
}

function ProjectCard({
  project,
  navigate,
  t,
}: {
  project: any
  navigate: any
  t: any
}) {
  return (
    <Card
      className="hover:shadow-md transition-all cursor-pointer group"
      onClick={() => navigate({ to: `/projects/${project.id}` })}
    >
      <CardHeader className="pb-3">
        <div className="flex justify-between items-start">
          <CardTitle className="text-base font-semibold group-hover:text-primary transition-colors line-clamp-1">
            {project.name}
          </CardTitle>
          {project.exists_locally ? (
            <Badge
              variant="outline"
              className="text-[10px] bg-green-500/5 text-green-600 border-green-200"
            >
              {t("dashboard.projects.local")}
            </Badge>
          ) : (
            <Badge variant="secondary" className="text-[10px]">
              {t("dashboard.projects.remote")}
            </Badge>
          )}
        </div>
        <CardDescription className="line-clamp-2 text-xs min-h-[2.5em]">
          {project.description || t("projects.noDescription")}
        </CardDescription>
      </CardHeader>
      <CardContent className="pb-3">
        <div className="flex items-center text-xs text-muted-foreground gap-2">
          <HardDrive className="h-3 w-3" />
          <span className="truncate max-w-[200px]">{project.path}</span>
        </div>
      </CardContent>
      <CardFooter className="pt-0">
        <Button
          variant="ghost"
          size="sm"
          className="w-full text-xs h-7 opacity-0 group-hover:opacity-100 transition-opacity bg-primary/5 hover:bg-primary/10"
          onClick={(e) => {
            e.stopPropagation()
            navigate({ to: `/projects/${project.id}` })
          }}
        >
          {t("dashboard.projects.openWorkspace")}{" "}
          <ExternalLink className="ml-2 h-3 w-3" />
        </Button>
      </CardFooter>
    </Card>
  )
}
