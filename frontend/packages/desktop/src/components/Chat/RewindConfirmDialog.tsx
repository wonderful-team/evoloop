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
import { Checkbox } from "@evoloop/shared/components/ui/checkbox"
import { Label } from "@evoloop/shared/components/ui/label"
import { useState } from "react"
import { useTranslation } from "react-i18next"

interface RewindConfirmDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  onConfirm: (revertFiles: boolean) => void
  mode?: "rewind" | "retry"
}

export function RewindConfirmDialog({
  open,
  onOpenChange,
  onConfirm,
  mode = "rewind",
}: RewindConfirmDialogProps) {
  const { t } = useTranslation()
  const [revertFiles, setRevertFiles] = useState(true)

  const title =
    mode === "rewind"
      ? t("chat.rewind.confirmTitle")
      : t("chat.retry.confirmTitle")

  const description =
    mode === "rewind"
      ? t("chat.rewind.confirmDescription")
      : t("chat.retry.confirmDescription")

  return (
    <AlertDialog open={open} onOpenChange={onOpenChange}>
      <AlertDialogContent>
        <AlertDialogHeader>
          <AlertDialogTitle>{title}</AlertDialogTitle>
          <AlertDialogDescription>{description}</AlertDialogDescription>
        </AlertDialogHeader>

        <div className="flex items-center gap-3 py-4">
          <Checkbox
            id="revert-files"
            checked={revertFiles}
            onCheckedChange={(checked) => setRevertFiles(checked === true)}
          />
          <Label htmlFor="revert-files" className="text-sm cursor-pointer">
            {t("chat.rewind.revertFiles")}
            <span className="block text-xs text-muted-foreground">
              {t("chat.rewind.revertFilesHint")}
            </span>
          </Label>
        </div>

        <AlertDialogFooter>
          <AlertDialogCancel>{t("common.cancel")}</AlertDialogCancel>
          <AlertDialogAction onClick={() => onConfirm(revertFiles)}>
            {mode === "rewind"
              ? t("chat.rewind.confirm")
              : t("chat.retry.confirm")}
          </AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  )
}
