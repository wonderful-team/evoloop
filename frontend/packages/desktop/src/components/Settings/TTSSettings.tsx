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
import { Eye, EyeOff, Play, Volume2 } from "lucide-react"
import { useEffect, useState } from "react"
import { useTranslation } from "react-i18next"
import { useModelManager } from "@/hooks/useModelManager"
import { type TTSVoice, useAutoSpeak, useTTS } from "@/hooks/useTTS"
import { isTauri, safeInvoke } from "@/lib/tauri"
import { SettingsCard } from "./SettingsCard"
import { useSettings } from "./SettingsContext"

const TTS_ENGINES = [
  { id: "system", name: "System (say)", model: null },
  { id: "edge-tts", name: "Edge TTS", model: null },
  { id: "qwen-tts", name: "Qwen TTS", model: null },
  { id: "cosyvoice", name: "CosyVoice (本地)", model: "cosyvoice" },
]

export function TTSSettings() {
  const { t } = useTranslation()
  const { autoSpeak, toggleAutoSpeak: originalToggleAutoSpeak } = useAutoSpeak()
  const {
    voices,
    currentVoice,
    setCurrentVoice: originalSetCurrentVoice,
    speak,
    fetchVoices,
  } = useTTS()
  const { models } = useModelManager()
  const [isPlaying, setIsPlaying] = useState<string | null>(null)

  // Build model availability map
  const modelAvailable: Record<string, boolean> = {}
  for (const m of models) {
    modelAvailable[m.id] = m.available
  }

  // Filter engines: hide local engines if model not available
  const visibleEngines = TTS_ENGINES.filter((e) => {
    if (!e.model) return true // cloud engines always visible
    return modelAvailable[e.model] !== false // show if available or unknown
  })

  const [tempAutoSpeak, setTempAutoSpeak] = useState(autoSpeak)
  const [tempCurrentVoice, setTempCurrentVoice] = useState(currentVoice)
  const [tempSpeed, setTempSpeed] = useState(1.0)
  const [tempTtsEngine, setTempTtsEngine] = useState("system")
  const [tempQwenTtsApiKey, setTempQwenTtsApiKey] = useState("")
  const [showApiKey, setShowApiKey] = useState(false)

  const {
    setComponentDirty,
    registerSaveHandler,
    unregisterSaveHandler,
    registerResetHandler,
  } = useSettings()
  const [initialState, setInitialState] = useState<any>(null)

  const fetchConfig = async () => {
    let savedEngine = localStorage.getItem("evoloop_tts_engine") || "edge-tts"
    if (isTauri()) {
      try {
        const backendEngine = await safeInvoke<string>("get_tts_engine")
        if (backendEngine) {
          savedEngine = backendEngine
        }
      } catch (e) {
        console.error("Failed to get TTS engine:", e)
      }
    }
    const savedVoice = localStorage.getItem("evoloop_tts_voice") || currentVoice
    const savedSpeed = parseFloat(
      localStorage.getItem("evoloop_tts_speed") || "1.0",
    )
    const savedKey = localStorage.getItem("evoloop_qwen_tts_key") || ""

    setTempTtsEngine(savedEngine)
    setTempCurrentVoice(savedVoice)
    originalSetCurrentVoice(savedVoice)
    setTempSpeed(savedSpeed)
    setTempAutoSpeak(autoSpeak)
    setTempQwenTtsApiKey(savedKey)

    fetchVoices(savedEngine)

    setInitialState({
      autoSpeak,
      currentVoice: savedVoice,
      speed: savedSpeed,
      ttsEngine: savedEngine,
      qwenTtsApiKey: savedKey,
    })
  }

  useEffect(() => {
    fetchConfig()
  }, [])

  // Track dirty
  useEffect(() => {
    if (!initialState) return
    const dirty =
      tempAutoSpeak !== initialState.autoSpeak ||
      tempCurrentVoice !== initialState.currentVoice ||
      tempSpeed !== initialState.speed ||
      tempTtsEngine !== initialState.ttsEngine ||
      tempQwenTtsApiKey !== initialState.qwenTtsApiKey
    setComponentDirty("tts", dirty)
  }, [
    tempAutoSpeak,
    tempCurrentVoice,
    tempSpeed,
    tempTtsEngine,
    tempQwenTtsApiKey,
    initialState,
    setComponentDirty,
  ])

  const handleSpeedChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    setTempSpeed(parseFloat(e.target.value))
  }

  const handlePreview = async (voice: TTSVoice) => {
    setIsPlaying(voice.id)
    try {
      const isChinese =
        voice.id.includes("zh") ||
        voice.name.toLowerCase().includes("ting") ||
        voice.id.startsWith("zf_") ||
        voice.id === "中文女" ||
        voice.id === "中文男"
      const previewText = isChinese
        ? "您好，我是一个智能语音助手。我可以帮你回答问题、朗读文字、处理文档，还能用多种语言和声音与你交流。"
        : "Hello, I am an intelligent voice assistant. I can answer questions, read text aloud, process documents, and communicate with you in multiple languages and voices."
      await speak(previewText, { voiceId: voice.id, engine: tempTtsEngine })
    } finally {
      setIsPlaying(null)
    }
  }

  useEffect(() => {
    registerSaveHandler("tts", async () => {
      // 1. LocalStorage for fallback
      localStorage.setItem("evoloop_tts_engine", tempTtsEngine)
      localStorage.setItem("evoloop_tts_voice", tempCurrentVoice)
      localStorage.setItem("evoloop_tts_speed", String(tempSpeed))
      localStorage.setItem("evoloop_qwen_tts_key", tempQwenTtsApiKey)

      // 2. SSOT Backend System Config
      try {
        const { SystemService } = await import("@/client")
        await Promise.all([
          SystemService.updateSystemConfig({
            requestBody: { key: "TTS_ENGINE", value: tempTtsEngine },
          }),
          SystemService.updateSystemConfig({
            requestBody: { key: "TTS_VOICE", value: tempCurrentVoice },
          }),
          SystemService.updateSystemConfig({
            requestBody: { key: "TTS_SPEED", value: String(tempSpeed) },
          }),
          SystemService.updateSystemConfig({
            requestBody: { key: "QWEN_TTS_API_KEY", value: tempQwenTtsApiKey },
          }),
        ])
      } catch (err) {
        console.error("Failed to sync TTS config to backend DB:", err)
      }

      originalSetCurrentVoice(tempCurrentVoice)
      if (tempAutoSpeak !== autoSpeak) {
        originalToggleAutoSpeak()
      }
      if (isTauri()) {
        safeInvoke("set_tts_engine", { engine: tempTtsEngine }).catch(
          console.error,
        )
        safeInvoke("set_tts_voice", { voice: tempCurrentVoice }).catch(
          console.error,
        )
        safeInvoke("set_tts_speed", { speed: tempSpeed }).catch(console.error)
        safeInvoke("set_qwen_api_key", { key: tempQwenTtsApiKey }).catch(
          console.error,
        )
      }
    })
    registerResetHandler("tts", () => {
      if (initialState) {
        setTempAutoSpeak(initialState.autoSpeak)
        setTempCurrentVoice(initialState.currentVoice)
        setTempSpeed(initialState.speed)
        setTempTtsEngine(initialState.ttsEngine)
        setTempQwenTtsApiKey(initialState.qwenTtsApiKey)
      }
    })
    return () => {
      unregisterSaveHandler("tts")
    }
  }, [
    tempSpeed,
    tempCurrentVoice,
    tempAutoSpeak,
    tempTtsEngine,
    tempQwenTtsApiKey,
    initialState,
    registerSaveHandler,
    unregisterSaveHandler,
    registerResetHandler,
  ])

  const currentVoiceObj = voices.find((v) => v.id === tempCurrentVoice)

  return (
    <SettingsCard icon={Volume2} title={t("settings.tts.title")}>
      <div className="space-y-4">
        {/* Auto-speak toggle */}
        <div className="flex items-center justify-between">
          <Label
            className="text-sm font-medium cursor-pointer"
            htmlFor="auto-speak"
          >
            {t("settings.tts.autoSpeak")}
          </Label>
          <Switch
            id="auto-speak"
            checked={tempAutoSpeak}
            onCheckedChange={setTempAutoSpeak}
          />
        </div>

        {/* TTS Engine selection (first - determines available voices and behavior) */}
        <div className="space-y-2">
          <Label className="text-sm font-medium">TTS Engine</Label>
          <Select
            value={tempTtsEngine}
            onValueChange={(v) => {
              setTempTtsEngine(v)
              fetchVoices(v)
            }}
          >
            <SelectTrigger className="h-10">
              <SelectValue placeholder="TTS Engine" />
            </SelectTrigger>
            <SelectContent>
              {visibleEngines.map((engine) => {
                const needsModel = engine.model != null
                const modelAvail = engine.model
                  ? modelAvailable[engine.model]
                  : true
                const disabled = needsModel && modelAvail === false
                return (
                  <SelectItem
                    key={engine.id}
                    value={engine.id}
                    disabled={disabled}
                    className={
                      disabled ? "text-muted-foreground cursor-not-allowed" : ""
                    }
                  >
                    <span className="flex items-center gap-2">
                      <span>{engine.name}</span>
                      {disabled && (
                        <span className="text-xs text-muted-foreground">
                          ({t("settings.voice.modelNotAvailable")})
                        </span>
                      )}
                    </span>
                  </SelectItem>
                )
              })}
            </SelectContent>
          </Select>
        </div>

        {/* Qwen API Key Configuration */}
        {tempTtsEngine === "qwen-tts" && (
          <div className="space-y-2 p-4 bg-muted/10 border border-border/50 rounded-xl animate-in fade-in duration-200">
            <Label
              htmlFor="qwen-api-key"
              className="text-sm font-medium flex items-center justify-between"
            >
              <span>阿里云百炼 API Key</span>
            </Label>
            <div className="relative flex items-center">
              <input
                id="qwen-api-key"
                type={showApiKey ? "text" : "password"}
                value={tempQwenTtsApiKey}
                onChange={(e) => setTempQwenTtsApiKey(e.target.value)}
                className="flex-1 pl-3 pr-10 py-2 bg-background border border-border rounded-md text-sm focus:outline-none focus:ring-2 focus:ring-primary/20 transition-all focus:border-primary font-mono"
                placeholder="sk-..."
              />
              <button
                type="button"
                onClick={() => setShowApiKey(!showApiKey)}
                className="absolute right-3 text-muted-foreground hover:text-foreground transition-colors"
              >
                {showApiKey ? (
                  <EyeOff className="h-4 w-4" />
                ) : (
                  <Eye className="h-4 w-4" />
                )}
              </button>
            </div>
          </div>
        )}

        {/* Voice selection dropdown & Preview button on the same row */}
        <div className="space-y-2">
          <Label className="text-sm font-medium">
            {t("settings.tts.voice")}
          </Label>
          <div className="flex items-center gap-2">
            <Select
              value={tempCurrentVoice}
              onValueChange={setTempCurrentVoice}
            >
              <SelectTrigger className="h-10 flex-1">
                <SelectValue placeholder={t("settings.tts.voice")} />
              </SelectTrigger>
              <SelectContent className="max-h-72">
                {voices.map((voice) => (
                  <SelectItem key={voice.id} value={voice.id}>
                    <span className="flex items-center gap-2">
                      <span>{voice.name}</span>
                      <span className="text-xs text-muted-foreground">
                        ({voice.gender})
                      </span>
                    </span>
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>

            {currentVoiceObj && (
              <Button
                variant="outline"
                size="sm"
                onClick={() => handlePreview(currentVoiceObj)}
                disabled={isPlaying !== null}
                className="h-10 px-3 shrink-0"
              >
                {isPlaying !== null ? (
                  <Volume2 className="mr-1.5 h-4 w-4 animate-pulse" />
                ) : (
                  <Play className="mr-1.5 h-4 w-4" />
                )}
                {t("chat.tts.preview")}
              </Button>
            )}
          </div>
        </div>

        {/* Speed slider */}
        <div className="space-y-2">
          <Label className="text-sm font-medium">
            {t("settings.tts.speechRate")}
          </Label>
          <div className="flex items-center gap-3">
            <span className="text-xs text-muted-foreground w-6 text-right">
              0.5
            </span>
            <input
              type="range"
              min="0.5"
              max="2.0"
              step="0.1"
              value={tempSpeed}
              onChange={handleSpeedChange}
              className="w-full h-1.5 bg-muted rounded-lg appearance-none cursor-pointer accent-primary"
            />
            <span className="text-xs text-muted-foreground w-6">2.0</span>
          </div>
          <div className="flex justify-between text-[10px] uppercase tracking-tighter text-muted-foreground font-bold">
            <span>{t("settings.tts.slow")}</span>
            <span>{t("settings.tts.normal")}</span>
            <span>{t("settings.tts.fast")}</span>
          </div>
        </div>
      </div>
    </SettingsCard>
  )
}
