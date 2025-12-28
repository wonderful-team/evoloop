import DeleteConfirmation from "./DeleteConfirmation"
import { useTranslation } from "react-i18next"

const DeleteAccount = () => {
  const { t } = useTranslation()
  return (
    <div className="max-w-md mt-4 rounded-lg border border-destructive/50 p-4">
      <h3 className="font-semibold text-destructive">{t('settings.danger.title')}</h3>
      <p className="mt-1 text-sm text-muted-foreground">
        {t('settings.danger.description')}
      </p>
      <DeleteConfirmation />
    </div>
  )
}

export default DeleteAccount
