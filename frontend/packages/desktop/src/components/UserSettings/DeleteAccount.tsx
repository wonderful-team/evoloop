import { Trash2 } from "lucide-react"
import { useTranslation } from "react-i18next"
import { SettingsCard } from "@/components/Settings/SettingsCard"
import DeleteConfirmation from "./DeleteConfirmation"

const DeleteAccount = () => {
  const { t } = useTranslation()
  return (
    <div className="flex flex-col gap-8">
      <SettingsCard
        icon={Trash2}
        title={t("settings.danger.title")}
        description={t("settings.danger.description")}
        iconClassName="text-destructive bg-destructive/10"
      >
        <div className="flex flex-col items-start gap-4">
          <p className="text-sm text-muted-foreground">
            {t(
              "settings.danger.delete_warning",
              "Permanently delete your account and all associated data. This action is irreversible.",
            )}
          </p>
          <DeleteConfirmation />
        </div>
      </SettingsCard>
    </div>
  )
}

export default DeleteAccount
