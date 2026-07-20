import { Button } from "@evoloop/shared/components/ui/button"
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from "@evoloop/shared/components/ui/collapsible"
import { Label } from "@evoloop/shared/components/ui/label"
import { Switch } from "@evoloop/shared/components/ui/switch"
import { cn } from "@evoloop/shared/lib/utils"
import {
  AlertCircle,
  CheckCircle2,
  ChevronDown,
  Cpu,
  Download,
  Keyboard,
  Loader2,
  Mic,
  MousePointerClick,
  Power,
  Zap,
} from "lucide-react"
import { useEffect, useState } from "react"
import { useTranslation } from "react-i18next"
import { toast } from "sonner"
import {
  useTauriVoiceShortcut,
  useTauriVoiceShortcutSettings,
} from "@/hooks/useTauriVoiceShortcut"
import { useWakeWord, useWakeWordSettings } from "@/hooks/useWakeWord"
import { isTauri as checkIsTauri } from "@/lib/tauri"
import { SettingsCard } from "./SettingsCard"
import { useSettings } from "./SettingsContext"
import { ModelManager } from "./ModelManager"
import { TTSSettings } from "./TTSSettings"
import { useModelManager } from "@/hooks/useModelManager"

export function VoiceControlSettings() {
  const { t } = useTranslation()
  const { wakeWord, wakeWordEnabled, updateWakeWord, toggleWakeWord } =
    useWakeWordSettings()

  const {
    shortcutKey: sk,
    longPressThreshold,
    shortcutEnabled: se,
    updateShortcutKey,
    updateLongPressThreshold,
    toggleShortcut,
  } = useTauriVoiceShortcutSettings()

  const [tempWakeWord, setTempWakeWord] = useState(wakeWord)
  const [tempWakeWordEnabled, setTempWakeWordEnabled] =
    useState(wakeWordEnabled)
  const [tempShortcutKey, setTempShortcutKey] = useState(sk)
  const [tempLongPressThreshold, setTempLongPressThreshold] =
    useState(longPressThreshold)
  const [tempShortcutEnabled, setTempShortcutEnabled] =
    useState(se)

  const [isSupported, setIsSupported] = useState(true)
  const [isTauri, setIsTauri] = useState(false)
  const { models, startDownload } = useModelManager()
  const {
    setComponentDirty,
    registerSaveHandler,
    unregisterSaveHandler,
    registerResetHandler,
  } = useSettings()

  const [initialState, setInitialState] = useState<any>(null)

  const fetchSTTConfig = async () => {
    try {
      const state = {
        wakeWord,
        wakeWordEnabled,
        shortcutKey: sk,
        longPressThreshold,
        shortcutEnabled: se,
      }

      setTempWakeWord(wakeWord)
      setTempWakeWordEnabled(wakeWordEnabled)
      setTempShortcutKey(sk)
      setTempLongPressThreshold(longPressThreshold)
      setTempShortcutEnabled(se)

      setInitialState(state)
    } catch (error) {
      console.error("Failed to fetch STT config:", error)
    }
  }

  useEffect(() => {
    fetchSTTConfig()
  }, [
    wakeWord,
    wakeWordEnabled,
    sk,
    longPressThreshold,
    se,
  ])

  // Check dirty
  useEffect(() => {
    if (!initialState) return
    const isDirty =
      tempWakeWord !== initialState.wakeWord ||
      tempWakeWordEnabled !== initialState.wakeWordEnabled ||
      tempShortcutKey !== initialState.shortcutKey ||
      tempLongPressThreshold !== initialState.longPressThreshold ||
      tempShortcutEnabled !== initialState.shortcutEnabled

    setComponentDirty("voice", isDirty)
  }, [
    tempWakeWord,
    tempWakeWordEnabled,
    tempShortcutKey,
    tempLongPressThreshold,
    tempShortcutEnabled,
    initialState,
    setComponentDirty,
  ])

  // Check browser and Tauri support
  useEffect(() => {
    const SpeechRecognition =
      window.SpeechRecognition || window.webkitSpeechRecognition
    if (!SpeechRecognition) {
      setIsSupported(false)
    }
    if (checkIsTauri()) {
      setIsTauri(true)
    }
  }, [])

  // Register handlers
  useEffect(() => {
    registerSaveHandler("voice", () => Promise.resolve())
    registerResetHandler("voice", () => fetchSTTConfig())
    return () => unregisterSaveHandler("voice")
  }, [
    registerSaveHandler,
    unregisterSaveHandler,
    registerResetHandler,
    tempWakeWord,
    tempWakeWord,
    tempWakeWordEnabled,
    tempShortcutKey,
    tempLongPressThreshold,
    tempShortcutEnabled,
    initialState,
  ])

  // Wake word test (uses temp settings for preview)
  const {
    isListening: isWakeWordListening,
    isWakeWordDetected,
    transcript,
    startListening: startWakeWordListening,
    stopListening: stopWakeWordListening,
  } = useWakeWord({
    wakeWord: tempWakeWord,
    enabled: tempWakeWordEnabled,
    onWake: () => {
      toast.success(t("settings.voice.wakeWordDetected"))
    },
  })

  // Tauri shortcut test (uses temp settings for preview)
  const {
    setLongPressThreshold: setTauriLongPressThreshold,
    setShortcutKey: setTauriShortcutKey,
  } = useTauriVoiceShortcut({
    enabled: tempShortcutEnabled && isTauri,
    onPress: () => {
      toast.success(t("settings.voice.shortcutStarted"))
    },
  })

  // Sync temp shortcut settings with Tauri preview when changed
  useEffect(() => {
    if (isTauri && tempShortcutEnabled) {
      setTauriShortcutKey(tempShortcutKey).catch(console.error)
      setTauriLongPressThreshold(tempLongPressThreshold).catch(console.error)
    }
  }, [
    isTauri,
    tempShortcutKey,
    tempLongPressThreshold,
    tempShortcutEnabled,
  ])

  return (
    <div className="space-y-6">
      <TTSSettings />
      <ModelManager />

      <Collapsible className="border rounded-lg">
        <CollapsibleTrigger className="flex w-full items-center justify-between p-4 text-sm font-medium hover:bg-muted/20 transition-colors">
          <span>{t("settings.voice.advanced.title")}</span>
          <ChevronDown className="h-4 w-4 text-muted-foreground" />
        </CollapsibleTrigger>
        <CollapsibleContent>
          <div className="px-4 pb-4 space-y-6">
      {/* STT Engine Section */}
      <SettingsCard
        icon={Cpu}
        title={t("settings.voice.sttTitle") || "语音识别引擎"}
        description={t("settings.voice.sttDesc") || "语音识别引擎"}
      >
        <div className="space-y-4">
          <div className="flex items-center justify-between rounded-lg border p-3">
            <div className="flex-1 min-w-0">
              <div className="text-sm font-medium">Qwen3-ASR</div>
              <div className="text-xs text-muted-foreground mt-0.5">
                {t("settings.voice.sttDesc") || "本地离线识别，VAD 断句后触发"}
              </div>
            </div>
            <div className="shrink-0 ml-3">
              {(() => {
                const qwen = models.find((m) => m.id === "qwen3_asr")
                if (!qwen) return null
                if (qwen.downloaded)
                  return (
                    <span className="flex items-center gap-1 text-xs text-green-600">
                      <CheckCircle2 className="h-3 w-3" />
                      {t("settings.voice.modelDownloaded")}
                    </span>
                  )
                if (qwen.status === "downloading")
                  return (
                    <span className="flex items-center gap-1 text-xs text-blue-600">
                      <Loader2 className="h-3 w-3 animate-spin" />
                      {t("settings.voice.modelDownloading")} {qwen.progress != null ? `${Math.round(qwen.progress * 100)}%` : ""}
                    </span>
                  )
                return (
                  <Button
                    size="sm"
                    variant="outline"
                    onClick={() => startDownload("qwen3_asr")}
                  >
                    <Download className="h-3.5 w-3.5 mr-1" />
                    {t("settings.voice.modelDownloadBtn")} (954MB)
                  </Button>
                )
              })()}
            </div>
          </div>
        </div>
      </SettingsCard>

      {/* Wake Word Section */}
      {false && <SettingsCard
        icon={Mic}
        title={t("settings.voice.wakeWordTitle")}
        description={t("settings.voice.wakeWordDesc")}
      >
        <div className="space-y-4">
          {!isSupported && (
            <div className="flex items-start gap-3 p-4 bg-amber-500/10 border border-amber-500/20 rounded-xl text-sm text-amber-700 dark:text-amber-300">
              <AlertCircle className="h-5 w-5 shrink-0 mt-0.5 text-amber-500" />
              <p>{t("settings.voice.notSupported")}</p>
            </div>
          )}

          <div className="flex items-center justify-between p-4 bg-muted/10 border border-border/50 rounded-md transition-colors hover:bg-muted/20">
            <div className="flex items-center gap-4">
              <div
                className={cn(
                  "rounded-md p-2 transition-colors",
                  wakeWordEnabled && isSupported
                    ? "bg-primary/5 text-primary"
                    : "bg-muted text-muted-foreground",
                )}
              >
                <Power className="h-4 w-4" />
              </div>
              <div className="space-y-0.5">
                <Label
                  className="text-sm font-medium cursor-pointer"
                  htmlFor="wake-word-toggle"
                >
                  {t("settings.voice.enableWakeWord")}
                </Label>
                <p className="text-xs text-muted-foreground">
                  {t("settings.voice.enableWakeWordDesc")}
                </p>
              </div>
            </div>
            <Switch
              id="wake-word-toggle"
              checked={tempWakeWordEnabled}
              onCheckedChange={setTempWakeWordEnabled}
              disabled={!isSupported}
            />
          </div>

          <div className="space-y-3">
            <Label className="text-sm font-medium">
              {t("settings.voice.wakeWordLabel")}
            </Label>
            <div className="flex gap-2">
              <input
                type="text"
                value={tempWakeWord}
                onChange={(e) => setTempWakeWord(e.target.value)}
                disabled={!isSupported}
                className="flex-1 px-3 py-2 bg-background border rounded-md text-sm focus:outline-none focus:ring-2 focus:ring-primary/20 transition-all focus:border-primary"
                placeholder={t("settings.voice.wakeWordPlaceholder")}
              />
            </div>
            <p className="text-xs text-muted-foreground italic">
              {t("settings.voice.wakeWordHint")}
            </p>
          </div>

          {isSupported && (
            <div className="space-y-4 p-5 border border-border/50 bg-muted/5 rounded-md">
              <Label className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
                {t("settings.voice.testWakeWord")}
              </Label>
              <div className="flex items-center gap-6">
                <Button
                  onClick={
                    isWakeWordListening
                      ? stopWakeWordListening
                      : startWakeWordListening
                  }
                  variant={isWakeWordListening ? "destructive" : "outline"}
                  className="w-40"
                >
                  {isWakeWordListening
                    ? t("settings.voice.stopListening")
                    : t("settings.voice.startListening")}
                </Button>
                <div className="flex-1">
                  {isWakeWordListening && (
                    <div className="flex items-center gap-3 text-sm animate-pulse">
                      <span className="relative flex h-3 w-3">
                        <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-red-400 opacity-75" />
                        <span className="relative inline-flex rounded-full h-3 w-3 bg-red-500" />
                      </span>
                      <span className="text-red-500 font-medium">
                        {t("settings.voice.listening")}
                      </span>
                    </div>
                  )}
                  {isWakeWordDetected && (
                    <div className="text-green-600 font-bold flex items-center gap-2 animate-in zoom-in-95">
                      <Zap className="h-4 w-4 fill-green-600" />
                      {t("settings.voice.wakeWordDetected")}
                    </div>
                  )}
                  {transcript && !isWakeWordDetected && (
                    <div className="text-sm text-muted-foreground italic">
                      {t("settings.voice.heard")}: "{transcript}"
                    </div>
                  )}
                </div>
              </div>
            </div>
          )}
        </div>
      </SettingsCard>}

      {/* Shortcut Section */}
      {false && <SettingsCard
        icon={MousePointerClick}
        title={t("settings.voice.shortcutTitle")}
        description={t("settings.voice.shortcutDesc")}
      >
        <div className="space-y-4">
          {!isTauri && (
            <div className="flex items-start gap-3 p-4 bg-amber-500/10 border border-amber-500/20 rounded-xl text-sm text-amber-700 dark:text-amber-300">
              <AlertCircle className="h-5 w-5 shrink-0 mt-0.5 text-amber-500" />
              <p>{t("settings.voice.tauriOnly")}</p>
            </div>
          )}

          <div className="flex items-center justify-between p-4 bg-muted/10 border border-border/50 rounded-md transition-colors hover:bg-muted/20">
            <div className="flex items-center gap-4">
              <div
                className={cn(
                  "rounded-md p-2 transition-colors",
                  se && isTauri
                    ? "bg-primary/5 text-primary"
                    : "bg-muted text-muted-foreground",
                )}
              >
                <Keyboard className="h-4 w-4" />
              </div>
              <div className="space-y-0.5">
                <Label
                  className="text-sm font-medium cursor-pointer"
                  htmlFor="shortcut-toggle"
                >
                  {t("settings.voice.enableShortcut")}
                </Label>
                <p className="text-xs text-muted-foreground">
                  {t("settings.voice.enableUnifiedDesc")}
                </p>
              </div>
            </div>
            <Switch
              id="shortcut-toggle"
              checked={tempShortcutEnabled}
              onCheckedChange={setTempShortcutEnabled}
              disabled={!isTauri}
            />
          </div>

          <div className="space-y-4">
            <Label className="text-sm font-medium">
              {t("settings.voice.shortcutKey")}
            </Label>
            <div className="grid grid-cols-4 sm:grid-cols-8 gap-2">
              {[
                "Ctrl",
                "Alt",
                "Shift",
                "Meta",
                "F1",
                "F2",
                "F3",
                "F4",
                "F5",
                "F6",
                "F7",
                "F8",
                "F9",
                "F10",
                "F11",
                "F12",
              ].map((key) => (
                <Button
                  key={key}
                  variant={tempShortcutKey === key ? "default" : "outline"}
                  onClick={() => setTempShortcutKey(key)}
                  disabled={!isTauri}
                  className="h-9 px-0"
                >
                  {key}
                </Button>
              ))}
            </div>
            <p className="text-xs text-muted-foreground italic">
              {t("settings.voice.unifiedHint", { key: tempShortcutKey })}
            </p>
          </div>

          <div className="space-y-6 pt-2">
            <div className="space-y-4">
              <div className="flex justify-between items-end">
                <Label className="text-sm font-medium">
                  {t("settings.voice.longPressThreshold")}
                </Label>
                <span className="text-sm font-bold text-primary">
                  {tempLongPressThreshold}
                  {t("common.ms")}
                </span>
              </div>
              <input
                type="range"
                min="200"
                max="1500"
                step="50"
                value={tempLongPressThreshold}
                onChange={(e) => {
                  setTempLongPressThreshold(parseInt(e.target.value, 10))
                }}
                disabled={!isTauri}
                className="w-full h-1.5 bg-muted rounded-lg appearance-none cursor-pointer accent-primary"
              />
              <div className="flex justify-between text-[10px] uppercase tracking-tighter text-muted-foreground font-bold">
                <span>{t("settings.voice.fast")}</span>
                <span>{t("settings.voice.normal")}</span>
                <span>{t("settings.voice.slow")}</span>
              </div>
            </div>
          </div>

          {isTauri && tempShortcutEnabled && (
            <div className="space-y-4 p-5 border bg-muted/10 rounded-xl">
              <Label className="text-sm font-semibold uppercase tracking-wider text-muted-foreground">
                {t("settings.voice.testShortcut")}
              </Label>
              <div className="flex items-center justify-center p-6 border-2 border-dashed rounded-lg bg-background/50">
                <div className="flex flex-col items-center gap-3 text-muted-foreground text-center">
                  <Keyboard className="h-10 w-10 opacity-20" />
                  <p className="text-sm max-w-[240px]">
                    {t("settings.voice.unifiedInstruction", { key: tempShortcutKey })}
                  </p>
                </div>
              </div>
            </div>
          )}
        </div>
      </SettingsCard>}
          </div>{/* end advanced content */}
        </CollapsibleContent>
      </Collapsible>
    </div>
  )
}
