import { useMutation } from "@tanstack/react-query"
import { BookOpen, MoreVertical, Trash2 } from "lucide-react"
import { useState } from "react"
import { Trans, useTranslation } from "react-i18next"
import { ProjectsService } from "@/client"
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
import { Button } from "@evoloop/shared/components/ui/button"
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuTrigger,
} from "@evoloop/shared/components/ui/dropdown-menu"
import useCustomToast from "@evoloop/shared/hooks/useCustomToast"
import { useProjectStore } from "@/stores/projectStore"
import { handleError } from "@/utils"

interface ProjectActionsProps {
  project: any
}

export function ProjectActions({ project }: ProjectActionsProps) {
  const { t } = useTranslation()
  const { showSuccessToast, showErrorToast } = useCustomToast()
  const { fetchProjects, currentProject, setProject } = useProjectStore()
  const [deleteOpen, setDeleteOpen] = useState(false)

  const deleteMutation = useMutation({
    mutationFn: (id: number) =>
      ProjectsService.deleteProject({ projectId: id }),
    onSuccess: () => {
      showSuccessToast(t("projects.actions.deleteSuccess"))
      setDeleteOpen(false)
      fetchProjects()

      // If deleted project was selected, clear selection
      if (currentProject?.id === project.id) {
        setProject(null as any)
        // Redirect logic should technically handle this in the main view
      }
    },
    onError: handleError.bind(showErrorToast),
  })

  const { mutate: handleGenerateWiki } = useMutation({
    mutationFn: async () => {
      const token = localStorage.getItem("access_token")
      const res = await fetch(`${import.meta.env.VITE_API_URL || "http://localhost:8000"}/api/v1/wiki/generate`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${token}`
        },
        body: JSON.stringify({ project_id: project.id, topic: "Full Documentation", force_regenerate: true }),
      })
      if (!res.ok) throw new Error("Failed to start generation")
      return res.json()
    },
    onSuccess: () => {
      showSuccessToast(t('wiki.toast.start'))
      fetchProjects()
    },
    onError: handleError.bind(showErrorToast),
  })

  return (
    <>
      <DropdownMenu>
        <DropdownMenuTrigger asChild>
          <Button variant="ghost" className="h-8 w-8 p-0">
            <span className="sr-only">Open menu</span>
            <MoreVertical className="h-4 w-4" />
          </Button>
        </DropdownMenuTrigger>
        <DropdownMenuContent align="end">
          <DropdownMenuLabel>{t("projects.actions.label")}</DropdownMenuLabel>
          <DropdownMenuItem
            className="text-destructive focus:text-destructive cursor-pointer"
            onClick={(e) => {
              e.stopPropagation() // Prevent card click
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
            <BookOpen className="mr-2 h-4 w-4" /> {project.has_wiki ? t('wiki.regenerate_action') : t('wiki.generate')}
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
    </>
  )
}
