import { Button } from "@evoloop/shared/components/ui/button"
import { Label } from "@evoloop/shared/components/ui/label"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@evoloop/shared/components/ui/select"
import { Switch } from "@evoloop/shared/components/ui/switch"
import { cn } from "@evoloop/shared/lib/utils"
import {
  AlertCircle,
  Cpu,
  Keyboard,
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
import { TTSSettings } from "./TTSSettings"

export function VoiceControlSettings() {
  const { t } = useTranslation()
  const { wakeWord, wakeWordEnabled, updateWakeWord, toggleWakeWord } =
    useWakeWordSettings()

  const {
    shortcutKey,
    triggerMode,
    doubleClickInterval,
    shortcutDuration,
    shortcutEnabled,
    updateShortcutKey,
    updateTriggerMode,
    updateDoubleClickInterval,
    updateShortcutDuration,
    toggleShortcut,
  } = useTauriVoiceShortcutSettings()

  const [tempWakeWord, setTempWakeWord] = useState(wakeWord)
  const [tempWakeWordEnabled, setTempWakeWordEnabled] =
    useState(wakeWordEnabled)
  const [tempShortcutKey, setTempShortcutKey] = useState(shortcutKey)
  const [tempTriggerMode, setTempTriggerMode] = useState(triggerMode)
  const [tempDoubleClickInterval, setTempDoubleClickInterval] =
    useState(doubleClickInterval)
  const [tempShortcutDuration, setTempShortcutDuration] =
    useState(shortcutDuration)
  const [tempShortcutEnabled, setTempShortcutEnabled] =
    useState(shortcutEnabled)

  const [isSupported, setIsSupported] = useState(true)
  const [isTauri, setIsTauri] = useState(false)
  const [sttModel, setSttModel] = useState("paraformer-zh")
  const [sttDevice, setSttDevice] = useState("cpu")
  const [sttLoading, setSttLoading] = useState(false)
  const {
    setComponentDirty,
    registerSaveHandler,
    unregisterSaveHandler,
    registerResetHandler,
  } = useSettings()

  const [initialState, setInitialState] = useState<any>(null)

  const fetchSTTConfig = async () => {
    try {
      const { SystemService } = await import("@/client")
      const config: any = await SystemService.getSystemConfig()
      let model = "paraformer-zh"
      let device = "cpu"
      if (Array.isArray(config)) {
        const modelItem = config.find(
          (item: any) => item.key === "FUNASR_MODEL",
        )
        const deviceItem = config.find(
          (item: any) => item.key === "FUNASR_DEVICE",
        )
        if (modelItem) model = modelItem.value
        if (deviceItem) device = deviceItem.value
      }
      setSttModel(model)
      setSttDevice(device)

      const state = {
        sttModel: model,
        sttDevice: device,
        wakeWord,
        wakeWordEnabled,
        shortcutKey,
        triggerMode,
        doubleClickInterval,
        shortcutDuration,
        shortcutEnabled,
      }

      setTempWakeWord(wakeWord)
      setTempWakeWordEnabled(wakeWordEnabled)
      setTempShortcutKey(shortcutKey)
      setTempTriggerMode(triggerMode)
      setTempDoubleClickInterval(doubleClickInterval)
      setTempShortcutDuration(shortcutDuration)
      setTempShortcutEnabled(shortcutEnabled)

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
    shortcutKey,
    triggerMode,
    doubleClickInterval,
    shortcutDuration,
    shortcutEnabled,
  ])

  // Check dirty
  useEffect(() => {
    if (!initialState) return
    const isDirty =
      sttModel !== initialState.sttModel ||
      sttDevice !== initialState.sttDevice ||
      tempWakeWord !== initialState.wakeWord ||
      tempWakeWordEnabled !== initialState.wakeWordEnabled ||
      tempShortcutKey !== initialState.shortcutKey ||
      tempTriggerMode !== initialState.triggerMode ||
      tempDoubleClickInterval !== initialState.doubleClickInterval ||
      tempShortcutDuration !== initialState.shortcutDuration ||
      tempShortcutEnabled !== initialState.shortcutEnabled

    setComponentDirty("voice", isDirty)
  }, [
    sttModel,
    sttDevice,
    tempWakeWord,
    tempWakeWordEnabled,
    tempShortcutKey,
    tempTriggerMode,
    tempDoubleClickInterval,
    tempShortcutDuration,
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

  const handleSave = async () => {
    setSttLoading(true)
    try {
      const { SystemService } = await import("@/client")
      // 1. Save STT to backend
      await Promise.all([
        SystemService.updateSystemConfig({
          requestBody: { key: "FUNASR_MODEL", value: sttModel },
        }),
        SystemService.updateSystemConfig({
          requestBody: { key: "FUNASR_DEVICE", value: sttDevice },
        }),
      ])

      // 2. Save Wake Word (localStorage via hook)
      if (tempWakeWord !== wakeWord) updateWakeWord(tempWakeWord)
      if (tempWakeWordEnabled !== wakeWordEnabled) toggleWakeWord()

      // 3. Save Shortcut (localStorage + Tauri via hook)
      if (tempShortcutKey !== shortcutKey)
        await updateShortcutKey(tempShortcutKey)
      if (tempTriggerMode !== triggerMode)
        await updateTriggerMode(tempTriggerMode)
      if (tempDoubleClickInterval !== doubleClickInterval)
        await updateDoubleClickInterval(tempDoubleClickInterval)
      if (tempShortcutDuration !== shortcutDuration)
        await updateShortcutDuration(tempShortcutDuration)
      if (tempShortcutEnabled !== shortcutEnabled) await toggleShortcut()

      setInitialState({
        sttModel,
        sttDevice,
        wakeWord: tempWakeWord,
        wakeWordEnabled: tempWakeWordEnabled,
        shortcutKey: tempShortcutKey,
        triggerMode: tempTriggerMode,
        doubleClickInterval: tempDoubleClickInterval,
        shortcutDuration: tempShortcutDuration,
        shortcutEnabled: tempShortcutEnabled,
      })
    } catch (error) {
      toast.error(t("settings.voice.sttConfigError"))
      throw error
    } finally {
      setSttLoading(false)
    }
  }

  // Register handlers
  useEffect(() => {
    registerSaveHandler("voice", handleSave)
    registerResetHandler("voice", () => fetchSTTConfig())
    return () => unregisterSaveHandler("voice")
  }, [
    registerSaveHandler,
    unregisterSaveHandler,
    registerResetHandler,
    sttModel,
    sttDevice,
    tempWakeWord,
    tempWakeWordEnabled,
    tempShortcutKey,
    tempTriggerMode,
    tempDoubleClickInterval,
    tempShortcutDuration,
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
    isRecording: isShortcutRecording,
    setTriggerMode: setTauriTriggerMode,
    setDoubleClickInterval: setTauriDoubleClickInterval,
    setShortcutKey: setTauriShortcutKey,
    setShortcutDuration: setTauriShortcutDuration,
  } = useTauriVoiceShortcut({
    enabled: tempShortcutEnabled && isTauri,
    onShortcutStart: () => {
      toast.success(t("settings.voice.shortcutStarted"))
    },
    onShortcutEnd: () => {
      toast.info(t("settings.voice.shortcutEnded"))
    },
  })

  // Sync temp shortcut settings with Tauri preview when changed
  useEffect(() => {
    if (isTauri && tempShortcutEnabled) {
      setTauriShortcutKey(tempShortcutKey).catch(console.error)
      setTauriTriggerMode(tempTriggerMode).catch(console.error)
      setTauriDoubleClickInterval(tempDoubleClickInterval).catch(console.error)
      setTauriShortcutDuration(tempShortcutDuration).catch(console.error)
    }
  }, [
    isTauri,
    tempShortcutKey,
    tempTriggerMode,
    tempDoubleClickInterval,
    tempShortcutDuration,
    tempShortcutEnabled,
  ])

  const _handleToggleShortcut = () => {
    if (!isTauri) {
      toast.error(t("settings.voice.tauriRequired"))
      return
    }
    setTempShortcutEnabled(!tempShortcutEnabled)
  }

  return (
    <div className="space-y-6">
      <TTSSettings />

      <div className="h-px bg-border/50" />
      {/* STT Engine Section */}
      <SettingsCard
        icon={Cpu}
        title={t("settings.voice.sttTitle")}
        description={t("settings.voice.sttDesc")}
        headerExtra={
          sttLoading && (
            <div className="flex items-center gap-2 text-xs text-muted-foreground animate-pulse">
              <div className="h-3 w-3 animate-spin rounded-full border-2 border-current border-t-transparent" />
              {t("common.processing")}
            </div>
          )
        }
      >
        <div className="space-y-4">
          <div className="grid gap-6 md:grid-cols-2">
            <div className="space-y-2">
              <Label htmlFor="stt-model" className="text-sm font-medium">
                {t("settings.voice.sttModel")}
              </Label>
              <Select
                value={sttModel}
                onValueChange={(val) => {
                  setSttModel(val)
                  handleSaveSttConfig(val, sttDevice)
                }}
              >
                <SelectTrigger id="stt-model" className="h-10">
                  <SelectValue
                    placeholder={t("settings.voice.selectSttModel")}
                  />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="paraformer-zh">
                    paraformer-zh (Standard)
                  </SelectItem>
                  <SelectItem value="paraformer-zh-plus">
                    paraformer-zh-plus (Enhanced)
                  </SelectItem>
                  <SelectItem value="paraformer-zh-streaming">
                    paraformer-zh-streaming (Streaming)
                  </SelectItem>
                </SelectContent>
              </Select>
            </div>

            <div className="space-y-2">
              <Label htmlFor="stt-device" className="text-sm font-medium">
                {t("settings.voice.sttDevice")}
              </Label>
              <Select
                value={sttDevice}
                onValueChange={(val) => {
                  setSttDevice(val)
                  handleSaveSttConfig(sttModel, val)
                }}
              >
                <SelectTrigger id="stt-device" className="h-10">
                  <SelectValue
                    placeholder={t("settings.voice.selectSttDevice")}
                  />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="cpu">
                    <div className="flex items-center gap-2">
                      <Cpu className="h-4 w-4" />
                      <span>CPU</span>
                    </div>
                  </SelectItem>
                  <SelectItem value="cuda">
                    <div className="flex items-center gap-2">
                      <Zap className="h-4 w-4 text-amber-500" />
                      <span>CUDA (NVIDIA GPU)</span>
                    </div>
                  </SelectItem>
                </SelectContent>
              </Select>
            </div>
          </div>
        </div>
      </SettingsCard>

      {/* Wake Word Section */}
      <SettingsCard
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
      </SettingsCard>

      {/* Shortcut Section */}
      <SettingsCard
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
                  shortcutEnabled && isTauri
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
                  {triggerMode === "doubleClick"
                    ? t("settings.voice.enableDoubleClickDesc")
                    : t("settings.voice.enableLongPressDesc")}
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
              {t("settings.voice.triggerMode")}
            </Label>
            <div className="flex gap-4">
              <Button
                variant={
                  tempTriggerMode === "doubleClick" ? "default" : "outline"
                }
                onClick={() => setTempTriggerMode("doubleClick")}
                disabled={!isTauri}
                className="flex-1 h-12"
              >
                <MousePointerClick className="h-4 w-4 mr-2" />
                {t("settings.voice.doubleClick")}
              </Button>
              <Button
                variant={
                  tempTriggerMode === "longPress" ? "default" : "outline"
                }
                onClick={() => setTempTriggerMode("longPress")}
                disabled={!isTauri}
                className="flex-1 h-12"
              >
                <Keyboard className="h-4 w-4 mr-2" />
                {t("settings.voice.longPress")}
              </Button>
            </div>
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
              {tempTriggerMode === "doubleClick"
                ? t("settings.voice.doubleClickHint")
                : t("settings.voice.longPressHint")}
            </p>
          </div>

          <div className="space-y-6 pt-2">
            <div className="space-y-4">
              <div className="flex justify-between items-end">
                <Label className="text-sm font-medium">
                  {tempTriggerMode === "doubleClick"
                    ? t("settings.voice.doubleClickInterval")
                    : t("settings.voice.pressDuration")}
                </Label>
                <span className="text-sm font-bold text-primary">
                  {tempTriggerMode === "doubleClick"
                    ? tempDoubleClickInterval
                    : tempShortcutDuration}
                  ms
                </span>
              </div>
              <input
                type="range"
                min={tempTriggerMode === "doubleClick" ? "100" : "200"}
                max={tempTriggerMode === "doubleClick" ? "1000" : "2000"}
                step={tempTriggerMode === "doubleClick" ? "50" : "100"}
                value={
                  tempTriggerMode === "doubleClick"
                    ? tempDoubleClickInterval
                    : tempShortcutDuration
                }
                onChange={(e) => {
                  const val = parseInt(e.target.value, 10)
                  tempTriggerMode === "doubleClick"
                    ? setTempDoubleClickInterval(val)
                    : setTempShortcutDuration(val)
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

          {isTauri && shortcutEnabled && (
            <div className="space-y-4 p-5 border bg-muted/10 rounded-xl">
              <Label className="text-sm font-semibold uppercase tracking-wider text-muted-foreground">
                {t("settings.voice.testShortcut")}
              </Label>
              <div className="flex items-center justify-center p-6 border-2 border-dashed rounded-lg bg-background/50">
                {isShortcutRecording ? (
                  <div className="flex flex-col items-center gap-3 text-green-600 animate-in zoom-in-95">
                    <div className="relative flex h-12 w-12 items-center justify-center">
                      <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-green-400 opacity-75" />
                      <Mic className="h-8 w-8 relative" />
                    </div>
                    <span className="font-bold text-lg">
                      {t("settings.voice.recording")}
                    </span>
                  </div>
                ) : (
                  <div className="flex flex-col items-center gap-3 text-muted-foreground text-center">
                    <Keyboard className="h-10 w-10 opacity-20" />
                    <p className="text-sm max-w-[200px]">
                      {triggerMode === "doubleClick"
                        ? t("settings.voice.doubleClickInstruction", {
                            key: shortcutKey,
                          })
                        : t("settings.voice.longPressInstruction", {
                            key: shortcutKey,
                          })}
                    </p>
                  </div>
                )}
              </div>
            </div>
          )}
        </div>
      </SettingsCard>
    </div>
  )
}
