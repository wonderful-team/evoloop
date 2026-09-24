import {Badge} from "@evoloop/shared/components/ui/badge"
import {Button} from "@evoloop/shared/components/ui/button"
import {
    Card,
    CardContent,
    CardDescription,
    CardFooter,
    CardHeader,
    CardTitle,
} from "@evoloop/shared/components/ui/card"
import {useNavigate} from "@tanstack/react-router"
import {BookOpen, CheckCircle2, Clock, FolderOpen, Layers, ListTodo, RefreshCw, XCircle,} from "lucide-react"
import {useEffect} from "react"
import {useTranslation} from "react-i18next"
import type {Project} from "@/stores/projectStore"
import {useProjectStore} from "@/stores/projectStore"
import AddProject from "./AddProject"
import ImportProject from "./ImportProject"
import {ProjectActions} from "./ProjectActions"

// Helper to get indexing status display info
function getIndexingStatusDisplay(
  project: Project,
  t: (key: string) => string,
) {
  // Priority 1: Real-time Redis status (indexing)
  if (project.indexing_status === "indexing") {
    return {
      icon: <RefreshCw className="h-3 w-3 animate-spin" />,
      text: t("projects.status.indexing"),
      className: "bg-blue-500/10 text-blue-600 dark:text-blue-400 border-blue-500/20",
    }
  }

  // Priority 2: DB persisted status
  const dbStatus = project.db_indexing_status
  switch (dbStatus) {
    case "in_progress":
      return {
        icon: <RefreshCw className="h-3 w-3 animate-spin" />,
        text: t("projects.status.indexing"),
        className:
          "bg-blue-500/10 text-blue-600 dark:text-blue-400 border-blue-500/20",
      }
    case "completed":
      return {
        icon: <CheckCircle2 className="h-3 w-3" />,
        text: t("projects.status.indexed"),
        className:
          "bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 border-emerald-500/20",
      }
    case "failed":
      return {
        icon: <XCircle className="h-3 w-3" />,
        text: t("projects.status.indexFailed"),
        className: "bg-red-500/10 text-red-600 dark:text-red-400 border-red-500/20",
      }
    case "pending":
      return {
        icon: <Clock className="h-3 w-3" />,
        text: t("projects.status.indexPending"),
        className:
          "bg-amber-500/10 text-amber-600 dark:text-amber-400 border-amber-500/20",
      }
    default:
      return null
  }
}

export function ProjectList() {
  const { t } = useTranslation()
  const navigate = useNavigate()
  const {
    projects,
    fetchProjects,
    setProject,
    currentProject,
    isLoading: isListLoading,
  } = useProjectStore()

  // Trigger fetch on mount
  useEffect(() => {
    fetchProjects()
  }, [fetchProjects])

  const handleRefresh = () => {
    fetchProjects()
  }

  const handleSelect = (proj: any) => {
    setProject(proj)
    navigate({ to: `/projects/${proj.id}` })
  }

  const isLoading = isListLoading

  if (isListLoading && projects.length === 0) {
    return <div className="p-8">{t("projects.loading")}</div>
  }

  return (
    <div className="flex-1 h-full overflow-y-auto p-6 md:p-8">
      <div className="flex items-center justify-between mb-8">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">
            {t("projects.title")}
          </h1>
          <p className="text-muted-foreground">{t("projects.subtitle")}</p>
        </div>
        <div className="flex items-center gap-2">
          <Button
            variant="outline"
            onClick={handleRefresh}
            disabled={isLoading}
          >
            <RefreshCw
              className={`mr-2 h-4 w-4 ${isListLoading ? "animate-spin" : ""}`}
            />
            {t("projects.refresh")}
          </Button>

          <ImportProject />

          <AddProject />
        </div>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
        {projects.map((proj: any) => (
          <Card
            key={proj.id}
            className={`group relative hover:border-primary/50 transition-all cursor-pointer ${currentProject?.id === proj.id ? "border-primary ring-1 ring-primary" : ""}`}
            onClick={() => handleSelect(proj)}
          >
            <CardHeader className="flex flex-row items-start justify-between space-y-0 pb-2">
              <div className="p-2 bg-secondary rounded-md group-hover:bg-primary/10 group-hover:text-primary transition-colors">
                <FolderOpen className="h-5 w-5" />
              </div>
              <div className="flex items-center gap-2 flex-wrap">
                {/* Indexing Status */}
                {(() => {
                  const idxStatus = getIndexingStatusDisplay(proj, t)
                  if (!idxStatus) return null
                  return (
                    <Badge
                      variant="secondary"
                      className={`gap-1 ${idxStatus.className}`}
                      title={
                        proj.last_indexed_at
                          ? t("projects.status.lastIndexed", {
                              time: proj.last_indexed_at,
                            })
                          : undefined
                      }
                    >
                      {idxStatus.icon} {idxStatus.text}
                    </Badge>
                  )
                })()}
                {(proj.summarization_status === "running" ||
                  proj.summarization_status === "summarizing") && (
                  <Badge
                    variant="secondary"
                    className="bg-purple-500/10 text-purple-600 dark:text-purple-400 border-purple-500/20 gap-1"
                  >
                    <ListTodo className="h-3 w-3 animate-pulse" />{" "}
                    {t("projects.status.analyzing")}
                  </Badge>
                )}
                {proj.wiki_status === "running" && (
                  <Badge
                    variant="secondary"
                    className="bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 border-emerald-500/20 gap-1"
                  >
                    <BookOpen className="h-3 w-3 animate-pulse" />{" "}
                    {t("wiki.nav")}
                  </Badge>
                )}
                <div onClick={(e) => e.stopPropagation()}>
                  <ProjectActions project={proj} />
                </div>
              </div>
            </CardHeader>
            <CardContent>
              <CardTitle
                className="text-lg mb-2 truncate pr-2"
                title={proj.name}
              >
                {proj.name}
              </CardTitle>
              <CardDescription className="line-clamp-2 min-h-[40px]">
                {proj.description || t("projects.noDescription")}
              </CardDescription>
            </CardContent>
            <CardFooter className="text-xs text-muted-foreground flex justify-between">
              <span className="flex items-center gap-1">
                <Layers className="h-3 w-3" /> {proj.files_count || 0}{" "}
                {t("projects.filesCount")}
              </span>
              <span>
                {new Date(proj.created_at || Date.now()).toLocaleDateString()}
              </span>
            </CardFooter>
          </Card>
        ))}

        {/* Empty State */}
        {projects.length === 0 && (
          <div className="col-span-full text-center py-12 text-muted-foreground">
            {t("projects.emptyState")}
          </div>
        )}
      </div>
    </div>
  )
}
