import {
    DropdownMenu,
    DropdownMenuContent,
    DropdownMenuItem,
    DropdownMenuLabel,
    DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu"
import { Button } from "@/components/ui/button"
import { MoreVertical, Trash2 } from "lucide-react"
import { useMutation } from "@tanstack/react-query"
import { ProjectsService } from "@/client"
import useCustomToast from "@/hooks/useCustomToast"
import { handleError } from "@/utils"
import { useProjectStore } from "@/stores/projectStore"
import { useTranslation, Trans } from "react-i18next"

import {
    AlertDialog,
    AlertDialogAction,
    AlertDialogCancel,
    AlertDialogContent,
    AlertDialogDescription,
    AlertDialogFooter,
    AlertDialogHeader,
    AlertDialogTitle,
} from "@/components/ui/alert-dialog"
import { useState } from "react"

interface ProjectActionsProps {
    project: any
}

export function ProjectActions({ project }: ProjectActionsProps) {
    const { t } = useTranslation()
    const { showSuccessToast, showErrorToast } = useCustomToast()
    const { fetchProjects, currentProject, setProject } = useProjectStore()
    const [deleteOpen, setDeleteOpen] = useState(false)

    const deleteMutation = useMutation({
        mutationFn: (id: number) => ProjectsService.deleteProject({ projectId: id }),
        onSuccess: () => {
            showSuccessToast(t('projects.actions.deleteSuccess'))
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
                    <DropdownMenuLabel>{t('projects.actions.label')}</DropdownMenuLabel>
                    <DropdownMenuItem
                        className="text-destructive focus:text-destructive cursor-pointer"
                        onClick={(e) => {
                            e.stopPropagation() // Prevent card click
                            setDeleteOpen(true)
                        }}
                    >
                        <Trash2 className="mr-2 h-4 w-4" /> {t('projects.actions.delete')}
                    </DropdownMenuItem>
                </DropdownMenuContent>
            </DropdownMenu>

            <AlertDialog open={deleteOpen} onOpenChange={setDeleteOpen}>
                <AlertDialogContent onClick={(e) => e.stopPropagation()}>
                    <AlertDialogHeader>
                        <AlertDialogTitle>{t('projects.actions.confirmTitle')}</AlertDialogTitle>
                        <AlertDialogDescription>
                            <Trans
                                i18nKey="projects.actions.confirmDesc"
                                values={{ name: project.name }}
                                components={{ bold: <span className="font-bold" /> }}
                            />
                        </AlertDialogDescription>
                    </AlertDialogHeader>
                    <AlertDialogFooter>
                        <AlertDialogCancel onClick={(e) => e.stopPropagation()}>{t('common.cancel')}</AlertDialogCancel>
                        <AlertDialogAction
                            className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
                            onClick={(e) => {
                                e.stopPropagation()
                                deleteMutation.mutate(project.id)
                            }}
                        >
                            {deleteMutation.isPending ? t('projects.actions.deleting') : t('projects.actions.deleteConfirm')}
                        </AlertDialogAction>
                    </AlertDialogFooter>
                </AlertDialogContent>
            </AlertDialog>
        </>
    )
}
