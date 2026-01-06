import { useTranslation } from "react-i18next"
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card"
import DeleteConfirmation from "./DeleteConfirmation"

const DeleteAccount = () => {
  const { t } = useTranslation()
  return (
    <div className="flex flex-col gap-6 mt-4">
      <Card className="border-destructive/50">
        <CardHeader>
          <CardTitle className="text-destructive">
            {t("settings.danger.title")}
          </CardTitle>
          <CardDescription>{t("settings.danger.description")}</CardDescription>
        </CardHeader>
        <CardContent>
          <DeleteConfirmation />
        </CardContent>
      </Card>

      <Card className="border-orange-500/50">
        <CardHeader>
          <CardTitle className="text-orange-600">
            {t("settings.danger.kb_reset_title", "Knowledge Base Reset")}
          </CardTitle>
          <CardDescription>
            {t(
              "settings.danger.kb_reset_desc",
              "Wipe all indexed code and memory concepts. Use this if the AI seems confused or hallucinations persist.",
            )}
          </CardDescription>
        </CardHeader>
        <CardContent>
          <ResetKnowledgeConfirmation />
        </CardContent>
      </Card>
    </div>
  )
}

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
} from "@/components/ui/alert-dialog"
import { Button } from "@/components/ui/button"

const ResetKnowledgeConfirmation = () => {
  const { t } = useTranslation()
  const token = localStorage.getItem("access_token")

  const mutation = useMutation({
    mutationFn: () =>
      SystemService.resetKnowledgeBase({ authorization: `Bearer ${token}` }),
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
        t("settings.danger.kb_reset_error", "Failed to wipe Knowledge Base."),
      )
      console.error(err)
    },
  })

  return (
    <AlertDialog>
      <AlertDialogTrigger asChild>
        <Button
          variant="outline"
          className="mt-4 border-orange-200 text-orange-700 hover:bg-orange-50 hover:text-orange-800"
        >
          {t("settings.danger.kb_reset_btn", "Reset Knowledge Base")}
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
