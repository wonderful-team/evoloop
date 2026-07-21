import { Button } from "@evoloop/shared/components/ui/button"
import { Download, CheckCircle2, AlertCircle, Loader2, HardDrive } from "lucide-react"
import { useEffect } from "react"
import { useTranslation } from "react-i18next"
import { isTauri, safeInvoke } from "@/lib/tauri"
import { type ModelStatus, useModelManager } from "@/hooks/useModelManager"
import { SettingsCard } from "./SettingsCard"

export function ModelManager() {
  const { t } = useTranslation()
  const { models, loading, startDownload } = useModelManager()

  // Sync tray menu state when model availability changes
  useEffect(() => {
    if (!isTauri() || loading) return
    const qwenReady = models.find((m) => m.id === "qwen3_asr")?.available ?? false
    safeInvoke("sync_tray_voice_state", {
      mode: "off",
      voiceState: "idle",
      modelsReady: qwenReady,
    }).catch(() => {})
  }, [models, loading])

  if (loading) {
    return (
      <SettingsCard icon={HardDrive} title={t("settings.voice.models") || "语音模型"}>
        <div className="flex items-center gap-2 text-sm text-muted-foreground">
          <Loader2 className="h-4 w-4 animate-spin" />
          {t("common.loading") || "加载中..."}
        </div>
      </SettingsCard>
    )
  }

  if (models.length === 0) return null

  // Only show models that need manual download (ASR has its own section)
  const ttsModels = models.filter((m) => m.id !== "qwen3_asr")
  if (ttsModels.length === 0) return null

  return (
    <SettingsCard icon={HardDrive} title={t("settings.voice.models") || "语音模型"}>
      <div className="space-y-3">
        {ttsModels.map((model) => (
          <ModelItem
            key={model.id}
            model={model}
            onDownload={() => startDownload(model.id)}
          />
        ))}
      </div>
    </SettingsCard>
  )
}

function ModelItem({
  model,
  onDownload,
}: {
  model: ModelStatus
  onDownload: () => void
}) {
  const { t } = useTranslation()
  const isDownloading = model.status === "downloading"
  const isDownloaded = model.downloaded
  const isFailed = model.status === "failed"

  return (
    <div className="flex items-center justify-between rounded-lg border p-3">
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2">
          <span className="text-sm font-medium truncate">{model.name}</span>
          <span className="text-xs text-muted-foreground shrink-0">
            {model.size}
          </span>
        </div>
        <div className="flex items-center gap-2 mt-1">
          {isDownloaded ? (
            <span className="flex items-center gap-1 text-xs text-green-600">
              <CheckCircle2 className="h-3 w-3" />
              {t("settings.voice.modelDownloaded")}
            </span>
          ) : isFailed ? (
            <span className="flex items-center gap-1 text-xs text-red-600">
              <AlertCircle className="h-3 w-3" />
              {t("settings.voice.modelDownloadFailed")}
            </span>
          ) : isDownloading ? (
            <span className="flex items-center gap-1 text-xs text-blue-600">
              <Loader2 className="h-3 w-3 animate-spin" />
              {t("settings.voice.modelDownloading")}
            </span>
          ) : (
            <span className="text-xs text-muted-foreground">
              {t("settings.voice.modelNotDownloaded")}
            </span>
          )}
          {model.progress != null && (
            <span className="text-xs text-muted-foreground">
              {Math.round(model.progress * 100)}%
            </span>
          )}
        </div>
        {isDownloading && model.progress != null && (
          <div className="w-full bg-muted rounded-full h-1.5 mt-2">
            <div
              className="bg-primary h-1.5 rounded-full transition-all duration-500"
              style={{ width: `${Math.round(model.progress * 100)}%` }}
            />
          </div>
        )}
      </div>
      {!isDownloaded && !isDownloading && (
        <Button
          size="sm"
          variant="outline"
          onClick={onDownload}
          className="shrink-0 ml-3"
        >
          <Download className="h-3.5 w-3.5 mr-1" />
          {t("settings.voice.modelDownloadBtn")}
        </Button>
      )}
    </div>
  )
}
