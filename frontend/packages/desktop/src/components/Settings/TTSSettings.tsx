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
import { Play, Volume2, Eye, EyeOff } from "lucide-react"
import { useEffect, useState } from "react"
import { useTranslation } from "react-i18next"
import { type TTSVoice, useAutoSpeak, useTTS } from "@/hooks/useTTS"
import { SettingsCard } from "./SettingsCard"
import { isTauri, safeInvoke } from "@/lib/tauri"
import { useSettings } from "./SettingsContext"

const TTS_ENGINES = [
  { id: "system", name: "System (say)" },
  { id: "edge-tts", name: "Edge TTS" },
  { id: "qwen-tts", name: "Qwen TTS" },
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
  const [isPlaying, setIsPlaying] = useState<string | null>(null)

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

  useEffect(() => {
    fetchVoices(tempTtsEngine)
  }, []) // eslint-disable-line react-hooks/exhaustive-deps

  const fetchConfig = () => {
    const savedSpeed = parseFloat(
      localStorage.getItem("evoloop_tts_speed") || "1.0",
    )
    const savedKey = localStorage.getItem("evoloop_qwen_tts_key") || ""
    setTempSpeed(savedSpeed)
    setTempAutoSpeak(autoSpeak)
    setTempCurrentVoice(currentVoice)
    setTempQwenTtsApiKey(savedKey)

    setInitialState({
      autoSpeak,
      currentVoice,
      speed: savedSpeed,
      ttsEngine: tempTtsEngine,
      qwenTtsApiKey: savedKey,
    })
  }

  useEffect(() => {
    fetchConfig()
  }, [autoSpeak, currentVoice])

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
  }, [tempAutoSpeak, tempCurrentVoice, tempSpeed, tempTtsEngine, tempQwenTtsApiKey, initialState, setComponentDirty])

  const handleSpeedChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    setTempSpeed(parseFloat(e.target.value))
  }

  const handlePreview = async (voice: TTSVoice) => {
    setIsPlaying(voice.id)
    try {
      const isChinese =
        voice.id.toLowerCase().includes("zh") ||
        voice.name.toLowerCase().includes("ting")
      const previewText = isChinese
        ? "您好，我是一个智能语音助手。"
        : "Hello, how can I help you?"
      await speak(previewText, { voiceId: voice.id, engine: tempTtsEngine, apiKey: tempQwenTtsApiKey })
    } finally {
      setIsPlaying(null)
    }
  }

  useEffect(() => {
    registerSaveHandler("tts", async () => {
      localStorage.setItem("evoloop_tts_speed", String(tempSpeed))
      localStorage.setItem("evoloop_qwen_tts_key", tempQwenTtsApiKey)
      originalSetCurrentVoice(tempCurrentVoice)
      if (tempAutoSpeak !== autoSpeak) {
        originalToggleAutoSpeak()
      }
      if (isTauri()) {
        safeInvoke("set_tts_engine", { engine: tempTtsEngine }).catch(console.error)
        safeInvoke("set_tts_voice", { voice: tempCurrentVoice }).catch(console.error)
        safeInvoke("set_tts_speed", { speed: tempSpeed }).catch(console.error)
        safeInvoke("set_qwen_api_key", { key: tempQwenTtsApiKey }).catch(console.error)
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
      <SettingsCard
        icon={Volume2}
        title={t("settings.tts.title")}
      >
      <div className="space-y-4">
        {/* Auto-speak toggle */}
        <div className="flex items-center justify-between">
          <Label className="text-sm font-medium cursor-pointer" htmlFor="auto-speak">
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
          <Select value={tempTtsEngine} onValueChange={(v) => { setTempTtsEngine(v); fetchVoices(v) }}>
            <SelectTrigger className="h-10">
              <SelectValue placeholder="TTS Engine" />
            </SelectTrigger>
            <SelectContent>
              {TTS_ENGINES.map((engine) => (
                <SelectItem key={engine.id} value={engine.id}>
                  {engine.name}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>

        {/* Qwen API Key Configuration */}
        {tempTtsEngine === "qwen-tts" && (
          <div className="space-y-2 p-4 bg-muted/10 border border-border/50 rounded-xl animate-in fade-in duration-200">
            <Label htmlFor="qwen-api-key" className="text-sm font-medium flex items-center justify-between">
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

        {/* Voice selection dropdown */}
        <div className="space-y-3">
          <Label className="text-sm font-medium">{t("settings.tts.voice")}</Label>
          <Select value={tempCurrentVoice} onValueChange={setTempCurrentVoice}>
            <SelectTrigger className="h-10">
              <SelectValue placeholder={t("settings.tts.voice")} />
            </SelectTrigger>
            <SelectContent className="max-h-72">
              {voices.map((voice) => (
                <SelectItem key={voice.id} value={voice.id}>
                  <span className="flex items-center gap-2">
                    <span>{voice.name}</span>
                    <span className="text-xs text-muted-foreground">({voice.gender})</span>
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
              className="w-full h-9"
            >
              {isPlaying !== null ? (
                <Volume2 className="mr-2 h-4 w-4 animate-pulse" />
              ) : (
                <Play className="mr-2 h-4 w-4" />
              )}
              {t("chat.tts.preview")}
            </Button>
          )}

          <div className="flex items-start gap-3 p-4 bg-blue-500/5 border border-blue-500/10 rounded-xl text-sm text-blue-700/80 dark:text-blue-300/80">
            <Volume2 className="h-5 w-5 shrink-0 mt-0.5 text-blue-500" />
            <p className="leading-relaxed italic">{t("settings.tts.note")}</p>
          </div>
        </div>

        {/* Speed slider */}
        <div className="space-y-2">
          <Label className="text-sm font-medium">{t("settings.tts.speechRate")}</Label>
          <div className="flex items-center gap-3">
            <span className="text-xs text-muted-foreground w-6 text-right">0.5</span>
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
