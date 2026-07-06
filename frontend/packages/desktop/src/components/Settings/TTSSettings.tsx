import { Button } from "@evoloop/shared/components/ui/button"
import { Label } from "@evoloop/shared/components/ui/label"
import { Switch } from "@evoloop/shared/components/ui/switch"
import { cn } from "@evoloop/shared/lib/utils"
import { AlertCircle, Play, Sparkles, Volume2, VolumeX } from "lucide-react"
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
  const [speed, setSpeed] = useState(1.0)
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
    setSpeed(savedSpeed)
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
    const isDirty =
      tempAutoSpeak !== initialState.autoSpeak ||
      tempCurrentVoice !== initialState.currentVoice ||
      tempSpeed !== initialState.speed

    setComponentDirty("tts", isDirty)
  }, [
    tempAutoSpeak,
    tempCurrentVoice,
    tempSpeed,
    initialState,
    setComponentDirty,
  ])

  const handleSave = async () => {
    if (tempAutoSpeak !== autoSpeak) originalToggleAutoSpeak()
    if (tempCurrentVoice !== currentVoice)
      originalSetCurrentVoice(tempCurrentVoice)
    if (tempSpeed !== speed) {
      setSpeed(tempSpeed)
      localStorage.setItem("evoloop_tts_speed", tempSpeed.toString())
    }

    setInitialState({
      autoSpeak: tempAutoSpeak,
      currentVoice: tempCurrentVoice,
      speed: tempSpeed,
    })
  }

  // Register handlers
  useEffect(() => {
    registerSaveHandler("tts", handleSave)
    registerResetHandler("tts", () => fetchConfig())
    return () => unregisterSaveHandler("tts")
  }, [
    registerSaveHandler,
    unregisterSaveHandler,
    registerResetHandler,
    tempAutoSpeak,
    tempCurrentVoice,
    tempSpeed,
    initialState,
  ])

  const handleSpeedChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    setTempSpeed(parseFloat(e.target.value))
  }

  const handlePreview = async (voice: TTSVoice) => {
    if (isPlaying === voice.id) return

    setIsPlaying(voice.id)
    const text = voice.preview || t("chat.tts.preview")

    await speak(text, {
      voiceId: voice.id,
      speed: tempSpeed,
    })

    setIsPlaying(null)
  }

  const voiceDescriptions: Record<string, string> = {
    "zh-CN-XiaoxiaoNeural": t("settings.tts.voices.zhCNXiaoxiaoNeural"),
    "zh-CN-YunxiNeural": t("settings.tts.voices.zhCNYunxiNeural"),
    "zh-CN-YunjianNeural": t("settings.tts.voices.zhCNYunjianNeural"),
    "zh-CN-YunyangNeural": t("settings.tts.voices.zhCNYunyangNeural"),
    "zh-CN-XiaoyiNeural": t("settings.tts.voices.zhCNXiaoyiNeural"),
    "zh-CN-XiaohanNeural": t("settings.tts.voices.zhCNXiaohanNeural"),
    "zh-TW-HsiaoChenNeural": t("settings.tts.voices.zhTWHsiaoChenNeural"),
    "zh-HK-HiuMaanNeural": t("settings.tts.voices.zhHKHiuMaanNeural"),
    "en-US-AriaNeural": t("settings.tts.voices.enUSAriaNeural"),
    "en-US-GuyNeural": t("settings.tts.voices.enUSGuyNeural"),
    "ja-JP-NanamiNeural": t("settings.tts.voices.jaJPNanamiNeural"),
    "ko-KR-SunHiNeural": t("settings.tts.voices.koKRSunHiNeural"),
  }

  return (
    <div className="space-y-8">
      <SettingsCard
        icon={Volume2}
        title={t("settings.tts.title")}
        description={t("settings.tts.description")}
      >
        <div className="space-y-8">
          {/* Auto-speak toggle */}
          <div className="flex items-center justify-between p-4 bg-muted/10 border border-border/50 rounded-md transition-colors hover:bg-muted/20">
            <div className="flex items-center gap-4">
              <div
                className={cn(
                  "rounded-md p-2 transition-colors",
                  autoSpeak
                    ? "bg-primary/5 text-primary"
                    : "bg-muted text-muted-foreground",
                )}
              >
                {autoSpeak ? (
                  <Volume2 className="h-4 w-4" />
                ) : (
                  <VolumeX className="h-4 w-4" />
                )}
              </div>
              <div className="space-y-0.5">
                <Label
                  className="text-sm font-medium cursor-pointer"
                  htmlFor="auto-speak-toggle"
                >
                  {t("settings.tts.autoSpeak")}
                </Label>
                <p className="text-xs text-muted-foreground">
                  {t("settings.tts.autoSpeakDesc")}
                </p>
              </div>
            </div>
            <Switch
              id="auto-speak-toggle"
              checked={tempAutoSpeak}
              onCheckedChange={setTempAutoSpeak}
            />
          </div>

          {/* Speed control */}
          <div className="space-y-4">
            <div className="flex justify-between items-end">
              <Label className="text-sm font-medium">
                {t("settings.tts.speechRate")}
              </Label>
              <span className="text-sm font-bold text-primary px-2 py-0.5 bg-primary/10 rounded-md">
                {tempSpeed.toFixed(1)}
                {t("common.speedMultiplier")}
              </span>
            </div>
            <input
              type="range"
              min="0.5"
              max="2.0"
              step="0.1"
              value={tempSpeed}
              onChange={handleSpeedChange}
              className="w-full h-1.5 bg-muted rounded-lg appearance-none cursor-pointer accent-primary"
            />
            <div className="flex justify-between text-[10px] uppercase tracking-tighter text-muted-foreground font-bold">
              <span>{t("settings.tts.slow")}</span>
              <span>{t("settings.tts.normal")}</span>
              <span>{t("settings.tts.fast")}</span>
            </div>
          </div>
        </div>
      </SettingsCard>

      {/* Voice selection */}
      <SettingsCard
        icon={Sparkles}
        title={t("settings.tts.voice")}
        description={t("settings.tts.voiceDesc")}
      >
        <div className="space-y-3">
          {voices.map((voice) => (
            <div
              key={voice.id}
              className={cn(
                "group flex items-center justify-between p-4 rounded-md border transition-all duration-200",
                tempCurrentVoice === voice.id
                  ? "border-primary bg-primary/5"
                  : "border-border/50 bg-transparent hover:border-primary/20 hover:bg-muted/5",
              )}
              onClick={() => setTempCurrentVoice(voice.id)}
            >
              <div className="flex items-center gap-4 cursor-pointer">
                <div
                  className={cn(
                    "w-5 h-5 rounded-full border-2 flex items-center justify-center transition-colors",
                    tempCurrentVoice === voice.id
                      ? "border-primary"
                      : "border-muted-foreground/30 group-hover:border-primary/50",
                  )}
                >
                  {tempCurrentVoice === voice.id && (
                    <div className="w-2.5 h-2.5 rounded-full bg-primary animate-in zoom-in-50" />
                  )}
                </div>
                <div className="space-y-0.5">
                  <div className="flex items-center gap-2">
                    <span
                      className={cn(
                        "text-base font-semibold",
                        tempCurrentVoice === voice.id
                          ? "text-primary"
                          : "text-foreground",
                      )}
                    >
                      {voice.name}
                    </span>
                    <Badge
                      variant="outline"
                      className="text-[10px] px-1.5 py-0 uppercase h-4 opacity-70"
                    >
                      {voice.gender}
                    </Badge>
                  </div>
                  <p className="text-sm text-muted-foreground line-clamp-1">
                    {voiceDescriptions[voice.id] || voice.description}
                  </p>
                </div>
              </div>
              <Button
                variant={tempCurrentVoice === voice.id ? "secondary" : "ghost"}
                size="icon"
                onClick={(e) => {
                  e.stopPropagation()
                  handlePreview(voice)
                }}
                disabled={isPlaying === voice.id}
                className={cn(
                  "shrink-0 rounded-full h-10 w-10 transition-all",
                  isPlaying === voice.id ? "bg-primary/20 text-primary" : "",
                )}
              >
                {isPlaying === voice.id ? (
                  <div className="flex gap-0.5 items-center justify-center h-4">
                    <div
                      className="w-1 bg-primary h-2 animate-bounce"
                      style={{ animationDelay: "0ms" }}
                    />
                    <div
                      className="w-1 bg-primary h-3 animate-bounce"
                      style={{ animationDelay: "150ms" }}
                    />
                    <div
                      className="w-1 bg-primary h-2 animate-bounce"
                      style={{ animationDelay: "300ms" }}
                    />
                  </div>
                ) : (
                  <Play
                    className={cn(
                      "h-4 w-4",
                      currentVoice === voice.id
                        ? "fill-primary"
                        : "fill-muted-foreground",
                    )}
                  />
                )}
              </Button>
            </div>
          ))}

          {/* Info note */}
          <div className="flex items-start gap-3 mt-6 p-4 bg-blue-500/5 border border-blue-500/10 rounded-xl text-sm text-blue-700/80 dark:text-blue-300/80">
            <AlertCircle className="h-5 w-5 shrink-0 mt-0.5 text-blue-500" />
            <p className="leading-relaxed italic">{t("settings.tts.note")}</p>
          </div>
        </div>
      </SettingsCard>
    </div>
  )
}

function Badge({
  children,
  variant,
  className,
}: {
  children: React.ReactNode
  variant?: string
  className?: string
}) {
  return (
    <span
      className={cn(
        "inline-flex items-center rounded-md border px-2.5 py-0.5 text-xs font-semibold transition-colors focus:outline-none focus:ring-2 focus:ring-ring focus:ring-offset-2",
        variant === "secondary"
          ? "border-transparent bg-secondary text-secondary-foreground"
          : "text-foreground",
        className,
      )}
    >
      {children}
    </span>
  )
}
