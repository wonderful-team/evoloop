import { useTranslation } from "react-i18next"
import { EmbeddingSettings } from "./EmbeddingSettings"
import { LightningSettings } from "./LightningSettings"
import { LLMSettings } from "./LLMSettings"

export function ModelSettings() {
  const { t } = useTranslation()

  return (
    <div className="space-y-6">
      <LightningSettings />
      <div className="relative">
        <div className="absolute inset-0 flex items-center">
          <span className="w-full border-t" />
        </div>
        <div className="relative flex justify-center text-xs uppercase">
          <span className="bg-background px-2 text-muted-foreground">
            {t("settings.embedding.channel_separator")}
          </span>
        </div>
      </div>
      <EmbeddingSettings />
      <div className="relative">
        <div className="absolute inset-0 flex items-center">
          <span className="w-full border-t" />
        </div>
        <div className="relative flex justify-center text-xs uppercase">
          <span className="bg-background px-2 text-muted-foreground">
            {t("settings.lightning.channel_separator")}
          </span>
        </div>
      </div>
      <LLMSettings />
    </div>
  )
}
