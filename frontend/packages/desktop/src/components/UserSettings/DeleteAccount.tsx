import { useTranslation } from "react-i18next"
import { AlertTriangle, Trash2, RefreshCw } from "lucide-react"
import { SettingsCard } from "@/components/Settings/SettingsCard"
import { isTauri } from "@/lib/tauri"
import DeleteConfirmation from "./DeleteConfirmation"
import { useMutation } from "@tanstack/react-query"
import { toast } from "sonner"
import { SystemService } from "@/client"
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
  AlertDialogTrigger,
} from "@evoloop/shared/components/ui/alert-dialog"
import { Button } from "@evoloop/shared/components/ui/button"

const DeleteAccount = () => {
  const { t } = useTranslation()
  return (
    <div className="flex flex-col gap-8">
      {isTauri() && (
        <SettingsCard
          icon={AlertTriangle}
          title={t("settings.danger.kb_reset_title")}
          description={t("settings.danger.kb_reset_desc", "Wipe all indexed code and memory concepts. Use this if the AI seems confused or hallucinations persist.")}
          iconClassName="text-orange-600 bg-orange-600/10"
        >
          <div className="flex flex-col items-start gap-4">
            <p className="text-sm text-muted-foreground">
              {t("settings.danger.kb_reset_warning", "This action will force the system to rebuild its internal mapping of your project. Active chat sessions might lose some local context.")}
            </p>
            <ResetKnowledgeConfirmation />
          </div>
        </SettingsCard>
      )}

      <SettingsCard 
        icon={Trash2} 
        title={t("settings.danger.title")} 
        description={t("settings.danger.description")}
        iconClassName="text-destructive bg-destructive/10"
      >
        <div className="flex flex-col items-start gap-4">
          <p className="text-sm text-muted-foreground">
            {t("settings.danger.delete_warning", "Permanently delete your account and all associated data. This action is irreversible.")}
          </p>
          <DeleteConfirmation />
        </div>
      </SettingsCard>
    </div>
  )
}

const ResetKnowledgeConfirmation = () => {
  const { t } = useTranslation()

  const mutation = useMutation({
    mutationFn: () => SystemService.resetKnowledgeBase(),
    onSuccess: () => {
      toast.success(
        t(
          "settings.danger.kb_reset_success",
          "Knowledge Base wiped successfully.",
        ),
      )
    },
    onError: (err) => {
      toast.error(
        t("settings.danger.kb_reset_error"),
      )
      console.error(err)
    },
  })

  return (
    <AlertDialog>
      <AlertDialogTrigger asChild>
        <Button
          variant="outline"
          className="border-orange-200 text-orange-700 hover:bg-orange-50 transition-all gap-2"
        >
          <RefreshCw className="h-4 w-4" />
          {t("settings.danger.kb_reset_btn")}
        </Button>
      </AlertDialogTrigger>
      <AlertDialogContent>
        <AlertDialogHeader>
          <AlertDialogTitle>
            {t(
              "settings.danger.kb_reset_confirm_title",
              "Are you absolutely sure?",
            )}
          </AlertDialogTitle>
          <AlertDialogDescription>
            {t(
              "settings.danger.kb_reset_confirm_desc",
              "This will delete all indexed code, file summaries, and memory concepts. The system will need to re-index everything from scratch.",
            )}
          </AlertDialogDescription>
        </AlertDialogHeader>
        <AlertDialogFooter>
          <AlertDialogCancel>{t("common.cancel")}</AlertDialogCancel>
          <AlertDialogAction
            className="bg-orange-600 hover:bg-orange-700 focus:ring-orange-600"
            onClick={() => mutation.mutate()}
          >
            {t("common.confirm")}
          </AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  )
}

export default DeleteAccount

