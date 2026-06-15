import { Button } from "@evoloop/shared/components/ui/button"
import { cn } from "@evoloop/shared/lib/utils"
import { AlertCircle, Loader2, RotateCcw, Save } from "lucide-react"
import type React from "react"
import { useTranslation } from "react-i18next"
import { useSettings } from "./SettingsContext"

export const SettingsActionBar: React.FC = () => {
  const { t } = useTranslation()
  const { isDirty, isSaving, applyChanges, resetDraft } = useSettings()

  if (!isDirty && !isSaving) return null

  return (
    <div className="fixed bottom-6 inset-x-0 flex justify-center z-50 antialiased">
      <div className="bg-background border border-border shadow-lg rounded-full px-6 py-2 flex items-center gap-6">
        <div className="flex items-center gap-2 pr-4 border-r border-border mr-2">
          <AlertCircle className="h-4 w-4 text-amber-500" />
          <span className="text-sm font-medium whitespace-nowrap">
            {t("settings.pendingChanges")}
          </span>
        </div>

        <div className="flex items-center gap-3">
          <Button
            variant="ghost"
            size="sm"
            onClick={resetDraft}
            disabled={isSaving}
            className="text-muted-foreground hover:text-foreground"
          >
            <RotateCcw className="h-4 w-4 mr-2" />
            {t("settings.restoreBtn")}
          </Button>

          <Button
            size="sm"
            onClick={applyChanges}
            disabled={isSaving}
            className={cn("px-6", isSaving && "opacity-80")}
          >
            {isSaving ? (
              <Loader2 className="h-4 w-4 mr-2 animate-spin" />
            ) : (
              <Save className="h-4 w-4 mr-2" />
            )}
            {t("settings.applyChangesBtn")}
          </Button>
        </div>
      </div>
    </div>
  )
}
