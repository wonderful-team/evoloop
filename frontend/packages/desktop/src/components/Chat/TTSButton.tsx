import { Volume2, VolumeX, Loader2, Pause, Play, Settings2 } from 'lucide-react'
import { Button } from '@evoloop/shared/components/ui/button'
import { cn } from '@evoloop/shared/lib/utils'
import { useTTS, useAutoSpeak, TTSVoice } from '@/hooks/useTTS'
import { useTranslation } from 'react-i18next'
import { useEffect, useState } from 'react'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@evoloop/shared/components/ui/dropdown-menu'

interface TTSButtonProps {
  text: string
  className?: string
  size?: 'sm' | 'md' | 'lg'
  variant?: 'ghost' | 'secondary' | 'outline'
}

export function TTSButton({ 
  text, 
  className, 
  size = 'sm',
  variant = 'ghost'
}: TTSButtonProps) {
  const { t } = useTranslation()
  const { isSpeaking, isLoading, speak, stop } = useTTS()

  const handleClick = () => {
    if (isSpeaking) {
      stop()
    } else {
      speak(text)
    }
  }

  const sizeClasses = {
    sm: 'h-6 w-6',
    md: 'h-8 w-8',
    lg: 'h-10 w-10',
  }

  const iconSizes = {
    sm: 'h-3 w-3',
    md: 'h-4 w-4',
    lg: 'h-5 w-5',
  }

  return (
    <Button
      variant={variant}
      size="icon"
      className={cn(sizeClasses[size], className)}
      onClick={handleClick}
      title={isSpeaking ? t('chat.tts.stop', '停止朗读') : t('chat.tts.speak', '朗读')}
    >
      {isLoading ? (
        <Loader2 className={cn(iconSizes[size], 'animate-spin')} />
      ) : isSpeaking ? (
        <Pause className={iconSizes[size]} />
      ) : (
        <Volume2 className={iconSizes[size]} />
      )}
    </Button>
  )
}

interface TTSControlsProps {
  className?: string
}

export function TTSControls({ className }: TTSControlsProps) {
  const { t } = useTranslation()
  const { 
    voices, 
    currentVoice, 
    setCurrentVoice, 
    fetchVoices,
    speak,
  } = useTTS()
  const { autoSpeak, toggleAutoSpeak } = useAutoSpeak()
  const [speed, setSpeed] = useState(1.0)

  useEffect(() => {
    fetchVoices()
  }, [fetchVoices])

  const handlePreview = (voice: TTSVoice) => {
    const text = voice.preview || t('chat.tts.preview', '你好，我是语音助手。')
    speak(text, { voiceId: voice.id, speed })
  }

  const handleSpeedChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    setSpeed(parseFloat(e.target.value))
  }

  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button
          variant="ghost"
          size="icon"
          className={cn('h-8 w-8', className)}
          title={t('chat.tts.settings', '语音设置')}
        >
          <Settings2 className="h-4 w-4" />
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" className="w-64">
        <DropdownMenuLabel>{t('chat.tts.settings', '语音设置')}</DropdownMenuLabel>
        <DropdownMenuSeparator />
        
        {/* Auto-speak toggle */}
        <div className="flex items-center justify-between px-2 py-2">
          <span className="text-sm">{t('chat.tts.autoSpeak', '自动朗读')}</span>
          <button
            onClick={toggleAutoSpeak}
            className={cn(
              'relative inline-flex h-5 w-9 items-center rounded-full transition-colors',
              autoSpeak ? 'bg-primary' : 'bg-muted'
            )}
          >
            <span
              className={cn(
                'inline-block h-3 w-3 transform rounded-full bg-white transition-transform',
                autoSpeak ? 'translate-x-5' : 'translate-x-1'
              )}
            />
          </button>
        </div>
        
        <DropdownMenuSeparator />
        
        {/* Speed control */}
        <div className="px-2 py-2">
          <div className="flex justify-between mb-2">
            <span className="text-sm">{t('chat.tts.speed', '语速')}</span>
            <span className="text-sm text-muted-foreground">{speed.toFixed(1)}x</span>
          </div>
          <input
            type="range"
            min="0.5"
            max="2.0"
            step="0.1"
            value={speed}
            onChange={handleSpeedChange}
            className="w-full h-1.5 bg-muted rounded-lg appearance-none cursor-pointer accent-primary"
          />
          <div className="flex justify-between text-xs text-muted-foreground mt-1">
            <span>0.5x</span>
            <span>1.0x</span>
            <span>2.0x</span>
          </div>
        </div>
        
        <DropdownMenuSeparator />
        
        {/* Voice selection */}
        <DropdownMenuLabel className="text-xs">
          {t('chat.tts.voice', '选择音色')}
        </DropdownMenuLabel>
        {voices.map((voice) => (
          <DropdownMenuItem
            key={voice.id}
            className={cn(
              'flex items-center justify-between',
              currentVoice === voice.id && 'bg-accent'
            )}
            onClick={() => setCurrentVoice(voice.id)}
          >
            <div className="flex flex-col">
              <span className="font-medium">{voice.name}</span>
              <span className="text-xs text-muted-foreground">
                {t(`chat.tts.gender.${voice.gender}`, voice.gender)} · {voice.description}
              </span>
            </div>
            <Button
              variant="ghost"
              size="icon"
              className="h-6 w-6"
              onClick={(e) => {
                e.stopPropagation()
                handlePreview(voice)
              }}
            >
              <Play className="h-3 w-3" />
            </Button>
          </DropdownMenuItem>
        ))}
      </DropdownMenuContent>
    </DropdownMenu>
  )
}

interface AutoSpeakIndicatorProps {
  className?: string
}

export function AutoSpeakIndicator({ className }: AutoSpeakIndicatorProps) {
  const { t } = useTranslation()
  const { autoSpeak, toggleAutoSpeak } = useAutoSpeak()

  return (
    <Button
      variant={autoSpeak ? 'secondary' : 'ghost'}
      size="icon"
      className={cn('h-8 w-8', className)}
      onClick={toggleAutoSpeak}
      title={autoSpeak 
        ? t('chat.tts.autoSpeakOn', '自动朗读已开启') 
        : t('chat.tts.autoSpeakOff', '自动朗读已关闭')
      }
    >
      {autoSpeak ? (
        <Volume2 className="h-4 w-4 text-primary" />
      ) : (
        <VolumeX className="h-4 w-4 text-muted-foreground" />
      )}
    </Button>
  )
}
