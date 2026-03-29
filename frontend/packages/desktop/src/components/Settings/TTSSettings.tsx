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
    const text = voice.preview || t('chat.tts.preview', '你好，我是语音助手。')
    
    await speak(text, { 
      voiceId: voice.id, 
      speed,
    })
    
    setIsPlaying(null)
  }

  const voiceDescriptions: Record<string, string> = {
    'zh-CN-XiaoxiaoNeural': '温柔自然的女声，适合大多数场景（推荐）',
    'zh-CN-YunxiNeural': '年轻阳光的男声，清晰自然（推荐）',
    'zh-CN-YunjianNeural': '沉稳的男声，适合新闻播报风格',
    'zh-CN-YunyangNeural': '磁性沉稳的男声，成熟稳重',
    'zh-CN-XiaoyiNeural': '活泼年轻的女声，轻松愉快',
    'zh-CN-XiaohanNeural': '甜美可爱的女声，亲切友好',
    'zh-TW-HsiaoChenNeural': '台湾女声，温柔亲切',
    'zh-HK-HiuMaanNeural': '香港粤语女声，地道自然',
    'en-US-AriaNeural': '美式英语女声，标准清晰',
    'en-US-GuyNeural': '美式英语男声，自然流畅',
    'ja-JP-NanamiNeural': '日语女声，标准自然',
    'ko-KR-SunHiNeural': '韩语女声，温柔亲切',
  }

  return (
    <div className="space-y-6">
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Volume2 className="h-5 w-5" />
            {t('settings.tts.title', 'Text-to-Speech')}
          </CardTitle>
          <CardDescription>
            {t('settings.tts.description', 'Configure AI voice output settings')}
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
                {t('settings.tts.autoSpeak', 'Auto-speak AI responses')}
              </Label>
              <p className="text-sm text-muted-foreground">
                {t('settings.tts.autoSpeakDesc', 'Automatically read AI messages aloud when they arrive')}
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
                {t('settings.tts.speechRate', 'Speech Rate')}
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
              <span>{t('settings.tts.slow', 'Slow')}</span>
              <span>{t('settings.tts.normal', 'Normal')}</span>
              <span>{t('settings.tts.fast', 'Fast')}</span>
            </div>
          </div>
        </CardContent>
      </Card>

      {/* Voice selection */}
      <Card>
        <CardHeader>
          <CardTitle>{t('settings.tts.voice', 'Voice Selection')}</CardTitle>
          <CardDescription>
            {t('settings.tts.voiceDesc', 'Choose your preferred AI voice')}
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
              {t('settings.tts.note', 'TTS uses Microsoft Edge speech synthesis. Completely free, no API key required.')}
            </p>
          </div>
        </CardContent>
      </Card>
    </div>
  )
}
