import { Trans, useTranslation } from "react-i18next"
import { Button } from "@/components/ui/button"
import {
  Dialog,
  DialogClose,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog"
import { LoadingButton } from "@/components/ui/loading-button"
import { useMemberCancellation } from "@/hooks/useMemberCancellation"

const DeleteConfirmation = () => {
  const { t } = useTranslation()
  const { info, apply, cancel, isApplying, isCanceling, isLoading } =
    useMemberCancellation("desktop")

  // Status check: 0 or 1 usually implies pending/audit in Niushop logic
  const isPending = info && ((info as any).status === 0 || (info as any).status === 1)

  const handleAction = () => {
    if (isPending) {
      cancel(undefined, {
        onSuccess: () => {
          // Close dialog? automated by query invalidation re-rendering state
        },
      })
    } else {
      apply()
    }
  }

  if (isLoading)
    return (
      <Button disabled variant="outline">
        {t("deleteAccount.loading")}
      </Button>
    )

  if (isPending) {
    return (
      <div className="mt-3">
        <p className="text-sm text-yellow-600 mb-2">
          {t("deleteAccount.pendingReview")}
        </p>
        <Dialog>
          <DialogTrigger asChild>
            <Button
              variant="outline"
              className="border-red-200 text-red-600 hover:bg-red-50"
            >
              {t("deleteAccount.withdrawRequest")}
            </Button>
          </DialogTrigger>
          <DialogContent>
            <DialogHeader>
              <DialogTitle>{t("deleteAccount.withdrawTitle")}</DialogTitle>
              <DialogDescription>
                {t("deleteAccount.withdrawDescription")}
              </DialogDescription>
            </DialogHeader>
            <DialogFooter className="mt-4">
              <DialogClose asChild>
                <Button variant="outline">{t("deleteAccount.cancel")}</Button>
              </DialogClose>
              <LoadingButton
                variant="default"
                onClick={handleAction}
                loading={isCanceling}
              >
                {t("deleteAccount.confirmWithdraw")}
              </LoadingButton>
            </DialogFooter>
          </DialogContent>
        </Dialog>
      </div>
    )
  }

  return (
    <Dialog>
      <DialogTrigger asChild>
        <Button variant="destructive" className="mt-3">
          {t("deleteAccount.deleteButton")}
        </Button>
      </DialogTrigger>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{t("deleteAccount.deleteTitle")}</DialogTitle>
          <DialogDescription>
            <Trans
              i18nKey="deleteAccount.deleteDescription"
              components={{ bold: <strong />, br: <br /> }}
            />
          </DialogDescription>
        </DialogHeader>

        <DialogFooter className="mt-4">
          <DialogClose asChild>
            <Button variant="outline">{t("deleteAccount.cancel")}</Button>
          </DialogClose>
          <LoadingButton
            variant="destructive"
            onClick={handleAction}
            loading={isApplying}
          >
            {t("deleteAccount.confirmDelete")}
          </LoadingButton>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

export default DeleteConfirmation
