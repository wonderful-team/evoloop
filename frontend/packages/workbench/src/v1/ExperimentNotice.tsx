import { useState } from "react"
import { useTranslation } from "react-i18next"

import { Button } from "@evoloop/shared/components/ui/button"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@evoloop/shared/components/ui/dialog"

const ACK_KEY = "duty-experiment-notice-acked"

/** One-time experiment disclaimer shown when entering the autonomous duty page. */
export function ExperimentNotice() {
  const { t } = useTranslation()
  const [acked, setAcked] = useState(
    () => localStorage.getItem(ACK_KEY) === "1",
  )

  if (acked) return null

  return (
    <Dialog open onOpenChange={(o) => !o && setAcked(true)}>
      <DialogContent className="max-w-[420px]">
        <DialogHeader>
          <DialogTitle>{t("dutyBoard.notice.title")}</DialogTitle>
          <DialogDescription className="text-left leading-relaxed">
            {t("dutyBoard.notice.body")}
          </DialogDescription>
        </DialogHeader>
        <div className="flex justify-end gap-2">
          <Button
            variant="outline"
            size="sm"
            onClick={() => {
              window.history.back()
            }}
          >
            {t("dutyBoard.notice.leave")}
          </Button>
          <Button
            size="sm"
            onClick={() => {
              localStorage.setItem(ACK_KEY, "1")
              setAcked(true)
            }}
          >
            {t("dutyBoard.notice.understood")}
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  )
}
