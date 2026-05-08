import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Volume2, VolumeX, Play, AlertCircle } from 'lucide-react'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@evoloop/shared/components/ui/card'
import { Label } from '@evoloop/shared/components/ui/label'
import { Button } from '@evoloop/shared/components/ui/button'
import { cn } from '@evoloop/shared/lib/utils'
import { useAutoSpeak, useTTS, TTSVoice } from '@/hooks/useTTS'

export function TTSSettings() {
  const { t } = useTranslation()
  const { autoSpeak, toggleAutoSpeak } = useAutoSpeak()
  const { voices, currentVoice, setCurrentVoice, speak, fetchVoices } = useTTS()
  const [speed, setSpeed] = useState(1.0)
  const [isPlaying, setIsPlaying] = useState<string | null>(null)

  useEffect(() => {
    fetchVoices()
  }, [fetchVoices])

  // Load saved speed
  useEffect(() => {
    const savedSpeed = localStorage.getItem('evoloop_tts_speed')
    if (savedSpeed) {
      setSpeed(parseFloat(savedSpeed))
    }
  }, [])

  const handleSpeedChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const newSpeed = parseFloat(e.target.value)
    setSpeed(newSpeed)
    localStorage.setItem('evoloop_tts_speed', newSpeed.toString())
  }

  const handlePreview = async (voice: TTSVoice) => {
    if (isPlaying === voice.id) return
    
    setIsPlaying(voice.id)
    const text = voice.preview || t('chat.tts.preview')
    
    await speak(text, { 
      voiceId: voice.id, 
      speed,
    })
    
    setIsPlaying(null)
  }

  const voiceDescriptions: Record<string, string> = {
    'zh-CN-XiaoxiaoNeural': t('settings.tts.voices.zhCNXiaoxiaoNeural'),
    'zh-CN-YunxiNeural': t('settings.tts.voices.zhCNYunxiNeural'),
    'zh-CN-YunjianNeural': t('settings.tts.voices.zhCNYunjianNeural'),
    'zh-CN-YunyangNeural': t('settings.tts.voices.zhCNYunyangNeural'),
    'zh-CN-XiaoyiNeural': t('settings.tts.voices.zhCNXiaoyiNeural'),
    'zh-CN-XiaohanNeural': t('settings.tts.voices.zhCNXiaohanNeural'),
    'zh-TW-HsiaoChenNeural': t('settings.tts.voices.zhTWHsiaoChenNeural'),
    'zh-HK-HiuMaanNeural': t('settings.tts.voices.zhHKHiuMaanNeural'),
    'en-US-AriaNeural': t('settings.tts.voices.enUSAriaNeural'),
    'en-US-GuyNeural': t('settings.tts.voices.enUSGuyNeural'),
    'ja-JP-NanamiNeural': t('settings.tts.voices.jaJPNanamiNeural'),
    'ko-KR-SunHiNeural': t('settings.tts.voices.koKRSunHiNeural'),
  }

  return (
    <div className="space-y-6">
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Volume2 className="h-5 w-5" />
            {t('settings.tts.title')}
          </CardTitle>
          <CardDescription>
            {t('settings.tts.description')}
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-6">
          {/* Auto-speak toggle */}
          <div className="flex items-center justify-between p-4 bg-muted/50 rounded-lg">
            <div className="space-y-0.5">
              <Label className="text-base flex items-center gap-2">
                {autoSpeak ? (
                  <Volume2 className="h-4 w-4 text-primary" />
                ) : (
                  <VolumeX className="h-4 w-4 text-muted-foreground" />
                )}
                {t('settings.tts.autoSpeak')}
              </Label>
              <p className="text-sm text-muted-foreground">
                {t('settings.tts.autoSpeakDesc')}
              </p>
            </div>
            <button
              onClick={toggleAutoSpeak}
              className={cn(
                'relative inline-flex h-6 w-11 items-center rounded-full transition-colors',
                autoSpeak ? 'bg-primary' : 'bg-muted'
              )}
            >
              <span
                className={cn(
                  'inline-block h-4 w-4 transform rounded-full bg-white transition-transform',
                  autoSpeak ? 'translate-x-6' : 'translate-x-1'
                )}
              />
            </button>
          </div>

          {/* Speed control */}
          <div className="space-y-4">
            <div className="flex justify-between items-center">
              <Label className="text-base">
                {t('settings.tts.speechRate')}
              </Label>
              <span className="text-sm text-muted-foreground font-mono">
                {speed.toFixed(1)}x
              </span>
            </div>
            <input
              type="range"
              min="0.5"
              max="2.0"
              step="0.1"
              value={speed}
              onChange={handleSpeedChange}
              className="w-full h-2 bg-muted rounded-lg appearance-none cursor-pointer accent-primary"
            />
            <div className="flex justify-between text-xs text-muted-foreground">
              <span>{t('settings.tts.slow')}</span>
              <span>{t('settings.tts.normal')}</span>
              <span>{t('settings.tts.fast')}</span>
            </div>
          </div>
        </CardContent>
      </Card>

      {/* Voice selection */}
      <Card>
        <CardHeader>
          <CardTitle>{t('settings.tts.voice')}</CardTitle>
          <CardDescription>
            {t('settings.tts.voiceDesc')}
          </CardDescription>
        </CardHeader>
        <CardContent>
          <div className="space-y-2">
            {voices.map((voice) => (
              <div
                key={voice.id}
                className={cn(
                  'flex items-center justify-between p-4 rounded-lg border cursor-pointer transition-colors',
                  currentVoice === voice.id 
                    ? 'border-primary bg-primary/5' 
                    : 'border-border hover:border-primary/50'
                )}
                onClick={() => setCurrentVoice(voice.id)}
              >
                <div className="flex items-start gap-3">
                  <div className={cn(
                    "mt-1 w-4 h-4 rounded-full border flex items-center justify-center",
                    currentVoice === voice.id ? "border-primary" : "border-muted-foreground"
                  )}>
                    {currentVoice === voice.id && (
                      <div className="w-2 h-2 rounded-full bg-primary" />
                    )}
                  </div>
                  <div className="space-y-1">
                    <Label 
                      className="text-base font-medium cursor-pointer"
                    >
                      {voice.name}
                      <span className="ml-2 text-xs text-muted-foreground font-normal capitalize">
                        ({voice.gender})
                      </span>
                    </Label>
                    <p className="text-sm text-muted-foreground">
                      {voiceDescriptions[voice.id] || voice.description}
                    </p>
                  </div>
                </div>
                <Button
                  variant="ghost"
                  size="icon"
                  onClick={(e) => {
                    e.stopPropagation()
                    handlePreview(voice)
                  }}
                  disabled={isPlaying === voice.id}
                  className="shrink-0"
                >
                  {isPlaying === voice.id ? (
                    <span className="h-4 w-4 animate-pulse">●</span>
                  ) : (
                    <Play className="h-4 w-4" />
                  )}
                </Button>
              </div>
            ))}
          </div>

          {/* Info note */}
          <div className="flex items-start gap-2 mt-4 p-3 bg-blue-500/10 rounded-lg text-sm text-blue-700 dark:text-blue-300">
            <AlertCircle className="h-4 w-4 shrink-0 mt-0.5" />
            <p>
              {t('settings.tts.note')}
            </p>
          </div>
        </CardContent>
      </Card>
    </div>
  )
}
