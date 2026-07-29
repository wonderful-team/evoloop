import { Button } from "@evoloop/shared/components/ui/button"
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from "@evoloop/shared/components/ui/collapsible"
import { Input } from "@evoloop/shared/components/ui/input"
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
  Radio,
  Sparkles,
  Volume2,
  Zap,
} from "lucide-react"
import { useCallback, useEffect, useState } from "react"
import { useTranslation } from "react-i18next"
import { toast } from "sonner"
import { useModelManager } from "@/hooks/useModelManager"
import {
  useTauriVoiceShortcut,
  useTauriVoiceShortcutSettings,
} from "@/hooks/useTauriVoiceShortcut"
import { useWakeWord, useWakeWordSettings } from "@/hooks/useWakeWord"
import { isTauri as checkIsTauri } from "@/lib/tauri"
import { ModelManager } from "./ModelManager"
import { SettingsCard } from "./SettingsCard"
import { useSettings } from "./SettingsContext"
import { TTSSettings } from "./TTSSettings"

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
  const [tempShortcutEnabled, setTempShortcutEnabled] = useState(se)

  // ── Seeduplex state (declared early to avoid TDZ in useEffects below) ────
  const [tempSeeduplexAppId, setTempSeeduplexAppId] = useState("")
  const [tempSeeduplexAccessKey, setTempSeeduplexAccessKey] = useState("")
  const [seeduplexConnected, setSeeduplexConnected] = useState(false)
  const [tempDictationLlmPolish, setTempDictationLlmPolish] = useState(true)

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
      // Fetch current Seeduplex and Dictation config values from backend
      let seeduplexAppId = ""
      let seeduplexAccessKey = ""
      let dictationLlmPolish = "true"
      try {
        const { SystemService } = await import("@/client")
        const configs = await SystemService.getSystemConfig()
        for (const c of Array.isArray(configs) ? configs : []) {
          if (c.key === "SEEDUPLEX_APP_ID") seeduplexAppId = c.value ?? ""
          if (c.key === "SEEDUPLEX_ACCESS_KEY") seeduplexAccessKey = c.value ?? ""
          if (c.key === "EVOLOOP_DICTATION_LLM_POLISH") dictationLlmPolish = c.value ?? "true"
        }
      } catch { /* not critical */ }

      const state = {
        wakeWord,
        wakeWordEnabled,
        shortcutKey: sk,
        longPressThreshold,
        shortcutEnabled: se,
        seeduplexAppId,
        seeduplexAccessKey,
        dictationLlmPolish: dictationLlmPolish === "true",
      }

      setTempWakeWord(wakeWord)
      setTempWakeWordEnabled(wakeWordEnabled)
      setTempShortcutKey(sk)
      setTempLongPressThreshold(longPressThreshold)
      setTempShortcutEnabled(se)
      setTempSeeduplexAppId(seeduplexAppId)
      setTempSeeduplexAccessKey(seeduplexAccessKey)
      setTempDictationLlmPolish(dictationLlmPolish === "true")

      setInitialState(state)
    } catch (error) {
      console.error("Failed to fetch STT config:", error)
    }
  }

  useEffect(() => {
    fetchSTTConfig()
  }, [wakeWord, wakeWordEnabled, sk, longPressThreshold, se])

  // Check dirty
  useEffect(() => {
    if (!initialState) return
    const isDirty =
      tempWakeWord !== initialState.wakeWord ||
      tempWakeWordEnabled !== initialState.wakeWordEnabled ||
      tempShortcutKey !== initialState.shortcutKey ||
      tempLongPressThreshold !== initialState.longPressThreshold ||
      tempShortcutEnabled !== initialState.shortcutEnabled ||
      tempSeeduplexAppId !== (initialState.seeduplexAppId ?? "") ||
      tempSeeduplexAccessKey !== (initialState.seeduplexAccessKey ?? "") ||
      tempDictationLlmPolish !== initialState.dictationLlmPolish

    setComponentDirty("voice", isDirty)
  }, [
    tempWakeWord,
    tempWakeWordEnabled,
    tempShortcutKey,
    tempLongPressThreshold,
    tempShortcutEnabled,
    tempSeeduplexAppId,
    tempSeeduplexAccessKey,
    tempDictationLlmPolish,
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
    registerSaveHandler("voice", async () => {
      try {
        const { SystemService } = await import("@/client")
        const tasks: Promise<any>[] = []

        // Always save the Dictation LLM Polish switch value
        tasks.push(
          SystemService.updateSystemConfig({
            requestBody: { key: "EVOLOOP_DICTATION_LLM_POLISH", value: tempDictationLlmPolish ? "true" : "false" },
          }),
        )

        if (tempSeeduplexAppId) {
          tasks.push(
            SystemService.updateSystemConfig({
              requestBody: { key: "SEEDUPLEX_APP_ID", value: tempSeeduplexAppId },
            }),
          )
        }
        if (tempSeeduplexAccessKey) {
          tasks.push(
            SystemService.updateSystemConfig({
              requestBody: { key: "SEEDUPLEX_ACCESS_KEY", value: tempSeeduplexAccessKey },
            }),
          )
        }

        // Persist wake word settings (localStorage + Rust)
        if (tempWakeWordEnabled !== wakeWordEnabled) {
          toggleWakeWord()
        }
        if (tempWakeWord !== wakeWord) {
          updateWakeWord(tempWakeWord)
        }
        // Directly start/stop the Rust detector
        if (tempWakeWordEnabled) {
          const voice = localStorage.getItem("evoloop_tts_voice") || undefined
          const { invoke } = await import("@tauri-apps/api/core")
          invoke("start_wake_word_listener", {
            word: tempWakeWord,
            voice,
          }).catch((e: any) => console.error("[wake] start failed:", e))
        } else if (wakeWordEnabled) {
          const { invoke } = await import("@tauri-apps/api/core")
          invoke("stop_wake_word_listener").catch(() => {})
        }

        await Promise.all(tasks)
      } catch (err) {
        console.error("Failed to save voice config:", err)
        throw err
      }
    })
    registerResetHandler("voice", () => fetchSTTConfig())
    return () => unregisterSaveHandler("voice")
  }, [
    registerSaveHandler,
    unregisterSaveHandler,
    registerResetHandler,
    tempWakeWord,
    tempWakeWordEnabled,
    tempShortcutKey,
    tempLongPressThreshold,
    tempShortcutEnabled,
    tempSeeduplexAppId,
    tempSeeduplexAccessKey,
    tempDictationLlmPolish,
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
  }, [isTauri, tempShortcutKey, tempLongPressThreshold, tempShortcutEnabled])

  // ── Seeduplex init ────────────────────────────────────────────
  useEffect(() => {
    // Listen for Seeduplex connection status from Tauri events
    let unlisten: (() => void) | undefined
    const setup = async () => {
      try {
        const { listen } = await import("@tauri-apps/api/event")
        const unsub = await listen<{ connected: boolean }>("seeduplex:status", (e) => {
          setSeeduplexConnected(e.payload?.connected === true)
        })
        unlisten = unsub

        // Listen for voice errors (e.g., mic not available)
        const unsubErr = await listen<{ message: string; code?: string }>("voice:error", (e) => {
          toast.error(e.payload.message || "麦克风不可用")
        })
        // Combine cleanup functions
        const orig = unlisten
        unlisten = () => { orig?.(); unsubErr(); }
      } catch { /* not in Tauri context */ }
    }
    setup()
    return () => { if (unlisten) unlisten() }
  }, [])

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
                      {t("settings.voice.sttDesc") ||
                        "本地离线识别，VAD 断句后触发"}
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
                            {t("settings.voice.modelDownloading")}{" "}
                            {qwen.progress != null
                              ? `${Math.round(qwen.progress * 100)}%`
                              : ""}
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

            {/* Seeduplex Section */}
            <SettingsCard
              icon={Radio}
              title="火山引擎 Seeduplex"
              description="端到端语音大模型（替代 ASR+TTS，需 API Key）"
            >
              <div className="space-y-4">
                <div className="space-y-3">
                  <Label className="text-sm font-medium">App ID</Label>
                  <Input
                    value={tempSeeduplexAppId}
                    onChange={(e) => setTempSeeduplexAppId(e.target.value)}
                    placeholder="从火山引擎控制台获取"
                    className="font-mono text-xs"
                  />
                </div>
                <div className="space-y-3">
                  <Label className="text-sm font-medium">Access Key</Label>
                  <Input
                    type="password"
                    value={tempSeeduplexAccessKey}
                    onChange={(e) => setTempSeeduplexAccessKey(e.target.value)}
                    placeholder="从火山引擎控制台获取"
                    className="font-mono text-xs"
                  />
                </div>
                <div className="flex items-center gap-2">
                  <span
                    className={cn(
                      "inline-flex items-center gap-1 text-xs",
                      seeduplexConnected ? "text-green-600" : "text-muted-foreground",
                    )}
                  >
                    <span className={cn(
                      "h-2 w-2 rounded-full",
                      seeduplexConnected ? "bg-green-500" : "bg-gray-300",
                    )} />
                    {seeduplexConnected ? "已连接" : "未连接（保存后生效）"}
                  </span>
                </div>
              </div>
            </SettingsCard>

            {/* Dictation Polish Section */}
            <SettingsCard
              icon={Sparkles}
              title="听写润色"
              description="听写完成后，进行错别字智能纠错与语言润色"
            >
              <div className="flex items-center justify-between p-4 bg-muted/10 border border-border/50 rounded-md transition-colors hover:bg-muted/20">
                <div className="flex items-center gap-4">
                  <div className="space-y-0.5">
                    <Label
                      className="text-sm font-medium cursor-pointer"
                      htmlFor="dictation-polish-toggle"
                    >
                      开启听写润色
                    </Label>
                    <p className="text-xs text-muted-foreground">
                      关闭后将直接输入原始语音转录文字
                    </p>
                  </div>
                </div>
                <Switch
                  id="dictation-polish-toggle"
                  checked={tempDictationLlmPolish}
                  onCheckedChange={setTempDictationLlmPolish}
                />
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
                        variant={
                          isWakeWordListening ? "destructive" : "outline"
                        }
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
            {false && (
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
                          variant={
                            tempShortcutKey === key ? "default" : "outline"
                          }
                          onClick={() => setTempShortcutKey(key)}
                          disabled={!isTauri}
                          className="h-9 px-0"
                        >
                          {key}
                        </Button>
                      ))}
                    </div>
                    <p className="text-xs text-muted-foreground italic">
                      {t("settings.voice.unifiedHint", {
                        key: tempShortcutKey,
                      })}
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
                          setTempLongPressThreshold(
                            parseInt(e.target.value, 10),
                          )
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
                            {t("settings.voice.unifiedInstruction", {
                              key: tempShortcutKey,
                            })}
                          </p>
                        </div>
                      </div>
                    </div>
                  )}
                </div>
              </SettingsCard>
            )}
          </div>
          {/* end advanced content */}
        </CollapsibleContent>
      </Collapsible>
    </div>
  )
}
