import { useNavigate } from "@tanstack/react-router"
import { BookOpen, FolderOpen, Layers, ListTodo, RefreshCw } from "lucide-react"
import { useEffect } from "react"
import { useTranslation } from "react-i18next"
import { useProjectStore } from "@/stores/projectStore"
import { Badge } from "@evoloop/shared/components/ui/badge"
import { Button } from "@evoloop/shared/components/ui/button"
import {
  Card,
  CardContent,
  CardDescription,
  CardFooter,
  CardHeader,
  CardTitle,
} from "@evoloop/shared/components/ui/card"
import AddProject from "./AddProject"
import { ProjectActions } from "./ProjectActions"

export function ProjectList() {
  const { t } = useTranslation()
  const navigate = useNavigate()
  const { projects, fetchProjects, setProject, currentProject, isLoading } =
    useProjectStore()

  // Trigger fetch on mount
  useEffect(() => {
    fetchProjects()
  }, [fetchProjects])

  const handleRefresh = () => {
    fetchProjects()
  }

  const handleSelect = (proj: any) => {
    setProject(proj)
    navigate({ to: `/projects/${proj.id}/tasks` })
  }

  if (isLoading && projects.length === 0) {
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
              className={`mr-2 h-4 w-4 ${isLoading ? "animate-spin" : ""}`}
            />
            {t("projects.refresh")}
          </Button>
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
              <div className="flex items-center gap-2">
                {proj.indexing_status === "indexing" && (
                  <Badge
                    variant="secondary"
                    className="bg-blue-100 text-blue-700 hover:bg-blue-200 border-blue-200 gap-1"
                  >
                    <RefreshCw className="h-3 w-3 animate-spin" />{" "}
                    {t("projects.status.indexing", "Indexing")}
                  </Badge>
                )}
                {(proj.summarization_status === "running" ||
                  proj.summarization_status === "SUMMARIZING") && (
                    <Badge variant="secondary" className="bg-purple-100 text-purple-700 hover:bg-purple-200 border-purple-200 gap-1">
                      <ListTodo className="h-3 w-3 animate-pulse" /> Analyzing
                    </Badge>
                  )}
                {proj.wiki_status === "running" && (
                  <Badge variant="secondary" className="bg-green-100 text-green-700 hover:bg-green-200 border-green-200 gap-1">
                    <BookOpen className="h-3 w-3 animate-pulse" /> {t("wiki.nav", "Wiki")}
                  </Badge>
                )}
                <Badge variant="outline">
                  {proj.status_text || t("projects.active")}
                </Badge>
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
