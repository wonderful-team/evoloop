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
import { Play, Volume2 } from "lucide-react"
import { useEffect, useState } from "react"
import { useTranslation } from "react-i18next"
import { type TTSVoice, useAutoSpeak, useTTS } from "@/hooks/useTTS"
import { SettingsCard } from "./SettingsCard"
import { useSettings } from "./SettingsContext"

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

  const {
    setComponentDirty,
    registerSaveHandler,
    unregisterSaveHandler,
    registerResetHandler,
  } = useSettings()
  const [initialState, setInitialState] = useState<any>(null)

  useEffect(() => {
    fetchVoices()
  }, [fetchVoices])

  const fetchConfig = () => {
    const savedSpeed = parseFloat(
      localStorage.getItem("evoloop_tts_speed") || "1.0",
    )
    setTempSpeed(savedSpeed)
    setTempAutoSpeak(autoSpeak)
    setTempCurrentVoice(currentVoice)

    setInitialState({
      autoSpeak,
      currentVoice,
      speed: savedSpeed,
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
      tempSpeed !== initialState.speed
    setComponentDirty("tts", dirty)
  }, [tempAutoSpeak, tempCurrentVoice, tempSpeed, initialState, setComponentDirty])

  const handleSpeedChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    setTempSpeed(parseFloat(e.target.value))
  }

  const handlePreview = async (voice: TTSVoice) => {
    setIsPlaying(voice.id)
    try {
      await speak("Hello, how can I help you?", { voiceId: voice.id })
    } finally {
      setIsPlaying(null)
    }
  }

  useEffect(() => {
    registerSaveHandler("tts", async () => {
      localStorage.setItem("evoloop_tts_speed", String(tempSpeed))
      originalSetCurrentVoice(tempCurrentVoice)
      if (tempAutoSpeak !== autoSpeak) {
        originalToggleAutoSpeak()
      }
    })
    registerResetHandler("tts", () => {
      if (initialState) {
        setTempAutoSpeak(initialState.autoSpeak)
        setTempCurrentVoice(initialState.currentVoice)
        setTempSpeed(initialState.speed)
      }
    })
    return () => {
      unregisterSaveHandler("tts")
    }
  }, [
    tempSpeed,
    tempCurrentVoice,
    tempAutoSpeak,
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
      </div>
    </SettingsCard>
  )
}
