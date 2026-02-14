import { useQuery } from "@tanstack/react-query"
import { useNavigate } from "@tanstack/react-router"
import { FolderOpen, Loader2 } from "lucide-react"
import { useTranslation } from "react-i18next"
import { ProjectsService } from "../client"
import { Button } from "@evoloop/shared/components/ui/button"
import {
  Card,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@evoloop/shared/components/ui/card"

export function ProjectsScreen() {
  const { t } = useTranslation()
  const navigate = useNavigate()
  const token = localStorage.getItem("evoloop_token")
  const isGuest = !token

  const { data, isLoading } = useQuery({
    queryKey: ["evoloop", "projects"],
    queryFn: async () => {
      const res = await ProjectsService.getProjects()
      return res.code >= 0 && res.data ? res.data : { list: [] }
    },
    enabled: !!token,
  })

  if (isGuest) {
    return (
      <div className="p-4 space-y-4 h-full flex flex-col">
        <div className="flex items-center justify-between">
          <h1 className="text-xl font-bold">{t("projects.title")}</h1>
        </div>

        <div className="flex-1 flex flex-col items-center justify-center space-y-6 text-center animate-in fade-in slide-in-from-bottom-4 duration-700">
          <div className="w-20 h-20 bg-muted/50 rounded-full flex items-center justify-center">
            <FolderOpen className="w-10 h-10 text-muted-foreground/50" />
          </div>
          <div className="max-w-xs space-y-2">
            <h3 className="text-lg font-semibold">
              {t("projects.guestTitle")}
            </h3>
            <p className="text-sm text-muted-foreground">
              {t("projects.guestDesc")}
            </p>
          </div>
          <div className="flex gap-3 w-full max-w-xs">
            <Button
              className="flex-1"
              onClick={() => navigate({ to: "/login" as any })}
            >
              {t("auth.login.submit")}
            </Button>
            <Button
              variant="outline"
              className="flex-1"
              onClick={() => navigate({ to: "/register" as any })}
            >
              {t("auth.login.signUp")}
            </Button>
          </div>
        </div>
      </div>
    )
  }

  const projects = (data as any)?.list || []

  const handleProjectClick = async (project: any) => {
    // If we have a preferred device/last selected device, we go there.
    if (project.device_id) {
      navigate({ to: `/chat/${project.device_id}` as any })
    } else {
      // If no device_id, go to devices list
      navigate({ to: "/devices" as any })
    }
  }

  return (
    <div className="p-4 bg-background min-h-full">
      <h1 className="text-xl font-bold mb-4">{t("projects.title")}</h1>

      {isLoading ? (
        <div className="flex justify-center p-8">
          <Loader2 className="w-6 h-6 animate-spin text-muted-foreground" />
        </div>
      ) : (
        <div className="grid gap-3">
          {projects.map((project: any) => (
            <Card
              key={project.project_id}
              onClick={() => handleProjectClick(project)}
              className="active:scale-[0.98] transition-transform"
            >
              <CardHeader className="p-4">
                <div className="flex items-center gap-3">
                  <div className="w-10 h-10 bg-primary/10 rounded-lg flex items-center justify-center text-primary">
                    <FolderOpen className="w-5 h-5" />
                  </div>
                  <div>
                    <CardTitle className="text-base">
                      {project.project_name}
                    </CardTitle>
                    <CardDescription className="text-xs mt-1">
                      {t("projects.id")}
                      {project.project_id}
                    </CardDescription>
                  </div>
                </div>
              </CardHeader>
            </Card>
          ))}
          {projects.length === 0 && (
            <div className="text-center text-muted-foreground text-sm py-8">
              {t("projects.noProjects")}
            </div>
          )}
        </div>
      )}
    </div>
  )
}
