import { toast } from "sonner"
import { useTranslation } from "react-i18next"

const useCustomToast = () => {
  const { t } = useTranslation()
  const showSuccessToast = (description: string) => {
    toast.success(t('toast.success'), {
      description,
    })
  }

  const showErrorToast = (description: string) => {
    toast.error(t('toast.error'), {
      description,
    })
  }

  return { showSuccessToast, showErrorToast }
}

export default useCustomToast
