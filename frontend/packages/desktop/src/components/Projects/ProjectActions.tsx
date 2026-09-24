import {
    AlertDialog,
    AlertDialogAction,
    AlertDialogCancel,
    AlertDialogContent,
    AlertDialogDescription,
    AlertDialogFooter,
    AlertDialogHeader,
    AlertDialogTitle,
} from "@evoloop/shared/components/ui/alert-dialog"
import {Button} from "@evoloop/shared/components/ui/button"
import {
    DropdownMenu,
    DropdownMenuContent,
    DropdownMenuItem,
    DropdownMenuLabel,
    DropdownMenuTrigger,
} from "@evoloop/shared/components/ui/dropdown-menu"
import useCustomToast from "@evoloop/shared/hooks/useCustomToast"
import {useMutation} from "@tanstack/react-query"
import {BookOpen, MoreVertical, Rocket, Trash2} from "lucide-react"
import {useState} from "react"
import {Trans, useTranslation} from "react-i18next"
import {ProjectsService, WikiService} from "@/client"
import {useProjectStore} from "@/stores/projectStore"
import {handleError} from "@/utils"
import {DiscoverDialog} from "./Modules/Overview/DiscoverDialog"

interface ProjectActionsProps {
  project: any
}

export function ProjectActions({ project }: ProjectActionsProps) {
  const { t } = useTranslation()
  const { showSuccessToast, showErrorToast } = useCustomToast()
  const { fetchProjects, currentProject, setProject } = useProjectStore()
  const [deleteOpen, setDeleteOpen] = useState(false)
  const [discoverOpen, setDiscoverOpen] = useState(false)

  const deleteMutation = useMutation({
    mutationFn: (id: number) =>
      ProjectsService.deleteProject({ projectId: id }),
    onSuccess: () => {
      showSuccessToast(t("projects.actions.deleteSuccess"))
      setDeleteOpen(false)
      fetchProjects()

      // If deleted project was selected, clear selection
      if (currentProject?.id === project.id) {
        setProject(null)
        // Redirect logic should technically handle this in the main view
      }
    },
    onError: handleError.bind(showErrorToast),
  })

  const { mutate: handleGenerateWiki } = useMutation({
    mutationFn: async () => {
      return WikiService.generateWiki({
        requestBody: {
          project_id: project.id,
          topic: t("wiki.topic.full_documentation"),
          force_regenerate: true,
        },
      })
    },
    onSuccess: () => {
      showSuccessToast(t("wiki.toast.start"))
      fetchProjects()
    },
    onError: handleError.bind(showErrorToast),
  })

  return (
    <>
      <DropdownMenu>
        <DropdownMenuTrigger asChild>
          <Button variant="ghost" className="h-8 w-8 p-0">
            <span className="sr-only">{t("common.openMenu")}</span>
            <MoreVertical className="h-4 w-4" />
          </Button>
        </DropdownMenuTrigger>
        <DropdownMenuContent align="end">
          <DropdownMenuLabel>{t("projects.actions.label")}</DropdownMenuLabel>
          <DropdownMenuItem
            className="text-destructive focus:text-destructive cursor-pointer"
            onClick={(e) => {
              e.stopPropagation()
              setDeleteOpen(true)
            }}
          >
            <Trash2 className="mr-2 h-4 w-4" /> {t("projects.actions.delete")}
          </DropdownMenuItem>
          <DropdownMenuItem
            className="cursor-pointer"
            onClick={(e) => {
              e.stopPropagation()
              handleGenerateWiki()
            }}
          >
            <BookOpen className="mr-2 h-4 w-4" />{" "}
            {project.has_wiki
              ? t("wiki.regenerate_action")
              : t("wiki.generate")}
          </DropdownMenuItem>
          <DropdownMenuItem
            className="cursor-pointer"
            onClick={(e) => {
              e.stopPropagation()
              setDiscoverOpen(true)
            }}
          >
            <Rocket className="mr-2 h-4 w-4" /> {t("chat.sidebar.deploy")}
          </DropdownMenuItem>
        </DropdownMenuContent>
      </DropdownMenu>

      <AlertDialog open={deleteOpen} onOpenChange={setDeleteOpen}>
        <AlertDialogContent onClick={(e) => e.stopPropagation()}>
          <AlertDialogHeader>
            <AlertDialogTitle>
              {t("projects.actions.confirmTitle")}
            </AlertDialogTitle>
            <AlertDialogDescription>
              <Trans
                i18nKey="projects.actions.confirmDesc"
                values={{ name: project.name }}
                components={{ bold: <span className="font-bold" /> }}
              />
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel onClick={(e) => e.stopPropagation()}>
              {t("common.cancel")}
            </AlertDialogCancel>
            <AlertDialogAction
              className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
              onClick={(e) => {
                e.stopPropagation()
                deleteMutation.mutate(project.id)
              }}
            >
              {deleteMutation.isPending
                ? t("projects.actions.deleting")
                : t("projects.actions.deleteConfirm")}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>

      <DiscoverDialog
        projectId={project.id}
        open={discoverOpen}
        onOpenChange={setDiscoverOpen}
        onDiscovered={() => fetchProjects()}
      />
    </>
  )
}
