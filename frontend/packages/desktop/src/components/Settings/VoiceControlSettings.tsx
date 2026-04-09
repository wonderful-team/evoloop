import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { toast } from 'sonner'
import { Mic, Keyboard, Power, AlertCircle, MousePointerClick } from 'lucide-react'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@evoloop/shared/components/ui/card'
import { Label } from '@evoloop/shared/components/ui/label'
import { Button } from '@evoloop/shared/components/ui/button'
import { cn } from '@evoloop/shared/lib/utils'
import { useWakeWord, useWakeWordSettings } from '@/hooks/useWakeWord'
import { useTauriVoiceShortcut, useTauriVoiceShortcutSettings } from '@/hooks/useTauriVoiceShortcut'

export function VoiceControlSettings() {
  const { t } = useTranslation()
  const {
    wakeWord,
    wakeWordEnabled,
    updateWakeWord,
    toggleWakeWord
  } = useWakeWordSettings()

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
    toggleShortcut
  } = useTauriVoiceShortcutSettings()

  const [tempWakeWord, setTempWakeWord] = useState(wakeWord)
  const [isSupported, setIsSupported] = useState(true)
  const [isTauri, setIsTauri] = useState(false)

  // Check browser and Tauri support
  useEffect(() => {
    const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition
    if (!SpeechRecognition) {
      setIsSupported(false)
    }
    // Check if running in Tauri
    if ((window as any).__TAURI__) {
      setIsTauri(true)
    }
  }, [])

  // Wake word test
  const {
    isListening: isWakeWordListening,
    isWakeWordDetected,
    transcript,
    startListening: startWakeWordListening,
    stopListening: stopWakeWordListening
  } = useWakeWord({
    wakeWord,
    enabled: wakeWordEnabled,
    onWake: () => {
      toast.success(t('settings.voice.wakeWordDetected'))
    }
  })

  // Tauri shortcut test
  const {
    isRecording: isShortcutRecording,
    setTriggerMode: setTauriTriggerMode,
    setDoubleClickInterval: setTauriDoubleClickInterval,
    setShortcutKey: setTauriShortcutKey,
    setShortcutDuration: setTauriShortcutDuration
  } = useTauriVoiceShortcut({
    enabled: shortcutEnabled && isTauri,
    onShortcutStart: () => {
      toast.success(t('settings.voice.shortcutStarted'))
    },
    onShortcutEnd: () => {
      toast.info(t('settings.voice.shortcutEnded'))
    }
  })

  // Sync shortcut settings with Tauri when changed
  useEffect(() => {
    if (isTauri && shortcutEnabled) {
      setTauriShortcutKey(shortcutKey).catch(console.error)
      setTauriTriggerMode(triggerMode).catch(console.error)
      setTauriDoubleClickInterval(doubleClickInterval).catch(console.error)
      setTauriShortcutDuration(shortcutDuration).catch(console.error)
    }
  }, [isTauri, shortcutKey, triggerMode, doubleClickInterval, shortcutDuration, shortcutEnabled])

  const handleSaveWakeWord = () => {
    updateWakeWord(tempWakeWord)
    toast.success(t('settings.voice.wakeWordSaved'))
  }

  const handleToggleShortcut = async () => {
    if (!isTauri) {
      toast.error(t('settings.voice.tauriRequired'))
      return
    }
    await toggleShortcut()
    toast.success(shortcutEnabled 
      ? t('settings.voice.shortcutDisabled')
      : t('settings.voice.shortcutEnabled')
    )
  }

  return (
    <div className="space-y-6">
      {/* Wake Word Section */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Mic className="h-5 w-5" />
            {t('settings.voice.wakeWordTitle')}
          </CardTitle>
          <CardDescription>
            {t('settings.voice.wakeWordDesc')}
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-6">
          {!isSupported && (
            <div className="flex items-start gap-2 p-3 bg-amber-500/10 rounded-lg text-sm text-amber-700 dark:text-amber-300">
              <AlertCircle className="h-4 w-4 shrink-0 mt-0.5" />
              <p>
                {t('settings.voice.notSupported')}
              </p>
            </div>
          )}

          {/* Enable toggle */}
          <div className="flex items-center justify-between p-4 bg-muted/50 rounded-lg">
            <div className="space-y-0.5">
              <Label className="text-base flex items-center gap-2">
                <Power className="h-4 w-4" />
                {t('settings.voice.enableWakeWord')}
              </Label>
              <p className="text-sm text-muted-foreground">
                {t('settings.voice.enableWakeWordDesc')}
              </p>
            </div>
            <button
              onClick={toggleWakeWord}
              disabled={!isSupported}
              className={cn(
                'relative inline-flex h-6 w-11 items-center rounded-full transition-colors',
                wakeWordEnabled && isSupported ? 'bg-primary' : 'bg-muted'
              )}
            >
              <span
                className={cn(
                  'inline-block h-4 w-4 transform rounded-full bg-white transition-transform',
                  wakeWordEnabled && isSupported ? 'translate-x-6' : 'translate-x-1'
                )}
              />
            </button>
          </div>

          {/* Wake word input */}
          <div className="space-y-3">
            <Label className="text-base">
              {t('settings.voice.wakeWordLabel')}
            </Label>
            <div className="flex gap-2">
              <input
                type="text"
                value={tempWakeWord}
                onChange={(e) => setTempWakeWord(e.target.value)}
                disabled={!isSupported}
                className="flex-1 px-3 py-2 bg-background border rounded-md text-sm focus:outline-none focus:ring-2 focus:ring-ring"
                placeholder={t('settings.voice.wakeWordPlaceholder')}
              />
              <Button
                onClick={handleSaveWakeWord}
                disabled={!isSupported || tempWakeWord === wakeWord}
                variant="secondary"
              >
                {t('common.save')}
              </Button>
            </div>
            <p className="text-xs text-muted-foreground">
              {t('settings.voice.wakeWordHint')}
            </p>
          </div>

          {/* Test section */}
          {isSupported && (
            <div className="space-y-3 p-4 border rounded-lg">
              <Label className="text-base">
                {t('settings.voice.testWakeWord')}
              </Label>
              <div className="flex items-center gap-4">
                <Button
                  onClick={isWakeWordListening ? stopWakeWordListening : startWakeWordListening}
                  variant={isWakeWordListening ? 'destructive' : 'default'}
                >
                  {isWakeWordListening
                    ? t('settings.voice.stopListening')
                    : t('settings.voice.startListening')}
                </Button>
                <div className="flex-1">
                  {isWakeWordListening && (
                    <div className="flex items-center gap-2 text-sm">
                      <span className="relative flex h-3 w-3">
                        <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-red-400 opacity-75"></span>
                        <span className="relative inline-flex rounded-full h-3 w-3 bg-red-500"></span>
                      </span>
                      <span className="text-muted-foreground">
                        {t('settings.voice.listening')}
                      </span>
                    </div>
                  )}
                  {isWakeWordDetected && (
                    <div className="text-green-600 font-medium">
                      ✓ {t('settings.voice.wakeWordDetected')}
                    </div>
                  )}
                  {transcript && !isWakeWordDetected && (
                    <div className="text-sm text-muted-foreground">
                      {t('settings.voice.heard')}: "{transcript}"
                    </div>
                  )}
                </div>
              </div>
            </div>
          )}
        </CardContent>
      </Card>

      {/* Double Click / Long Press Key Section */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <MousePointerClick className="h-5 w-5" />
            {t('settings.voice.shortcutTitle')}
          </CardTitle>
          <CardDescription>
            {t('settings.voice.shortcutDesc')}
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-6">
          {!isTauri && (
            <div className="flex items-start gap-2 p-3 bg-amber-500/10 rounded-lg text-sm text-amber-700 dark:text-amber-300">
              <AlertCircle className="h-4 w-4 shrink-0 mt-0.5" />
              <p>
                {t('settings.voice.tauriOnly')}
              </p>
            </div>
          )}

          {/* Enable toggle */}
          <div className="flex items-center justify-between p-4 bg-muted/50 rounded-lg">
            <div className="space-y-0.5">
              <Label className="text-base flex items-center gap-2">
                <Power className="h-4 w-4" />
                {t('settings.voice.enableShortcut')}
              </Label>
              <p className="text-sm text-muted-foreground">
                {triggerMode === 'doubleClick' 
                  ? t('settings.voice.enableDoubleClickDesc')
                  : t('settings.voice.enableLongPressDesc')
                }
              </p>
            </div>
            <button
              onClick={handleToggleShortcut}
              disabled={!isTauri}
              className={cn(
                'relative inline-flex h-6 w-11 items-center rounded-full transition-colors',
                shortcutEnabled && isTauri ? 'bg-primary' : 'bg-muted'
              )}
            >
              <span
                className={cn(
                  'inline-block h-4 w-4 transform rounded-full bg-white transition-transform',
                  shortcutEnabled && isTauri ? 'translate-x-6' : 'translate-x-1'
                )}
              />
            </button>
          </div>

          {/* Trigger mode selection */}
          <div className="space-y-3">
            <Label className="text-base">
              {t('settings.voice.triggerMode')}
            </Label>
            <div className="flex gap-2">
              <Button
                variant={triggerMode === 'doubleClick' ? 'default' : 'outline'}
                onClick={() => updateTriggerMode('doubleClick')}
                disabled={!isTauri}
                className="flex-1"
              >
                <MousePointerClick className="h-4 w-4 mr-2" />
                {t('settings.voice.doubleClick')}
              </Button>
              <Button
                variant={triggerMode === 'longPress' ? 'default' : 'outline'}
                onClick={() => updateTriggerMode('longPress')}
                disabled={!isTauri}
                className="flex-1"
              >
                <Keyboard className="h-4 w-4 mr-2" />
                {t('settings.voice.longPress')}
              </Button>
            </div>
          </div>

          {/* Key selection */}
          <div className="space-y-3">
            <Label className="text-base">
              {t('settings.voice.shortcutKey')}
            </Label>
            <div className="flex gap-2 flex-wrap">
              {['Ctrl', 'Alt', 'Shift', 'Meta', 'F1', 'F2', 'F3', 'F4', 'F5', 'F6', 'F7', 'F8', 'F9', 'F10', 'F11', 'F12'].map((key) => (
                <Button
                  key={key}
                  variant={shortcutKey === key ? 'default' : 'outline'}
                  onClick={() => updateShortcutKey(key)}
                  disabled={!isTauri}
                  className="flex-1 min-w-[60px]"
                >
                  {key}
                </Button>
              ))}
            </div>
            <p className="text-xs text-muted-foreground">
              {triggerMode === 'doubleClick' 
                ? t('settings.voice.doubleClickHint')
                : t('settings.voice.longPressHint')
              }
            </p>
          </div>

          {/* Double click interval (only for double click mode) */}
          {triggerMode === 'doubleClick' && (
            <div className="space-y-3">
              <div className="flex justify-between">
                <Label className="text-base">
                  {t('settings.voice.doubleClickInterval')}
                </Label>
                <span className="text-sm text-muted-foreground">{doubleClickInterval}ms</span>
              </div>
              <input
                type="range"
                min="100"
                max="1000"
                step="50"
                value={doubleClickInterval}
                onChange={(e) => updateDoubleClickInterval(parseInt(e.target.value))}
                disabled={!isTauri}
                className="w-full h-2 bg-muted rounded-lg appearance-none cursor-pointer accent-primary"
              />
              <div className="flex justify-between text-xs text-muted-foreground">
                <span>100ms ({t('settings.voice.fast')})</span>
                <span>500ms ({t('settings.voice.normal')})</span>
                <span>1000ms ({t('settings.voice.slow')})</span>
              </div>
            </div>
          )}

          {/* Long press duration (only for long press mode) */}
          {triggerMode === 'longPress' && (
            <div className="space-y-3">
              <div className="flex justify-between">
                <Label className="text-base">
                  {t('settings.voice.pressDuration')}
                </Label>
                <span className="text-sm text-muted-foreground">{shortcutDuration}ms</span>
              </div>
              <input
                type="range"
                min="200"
                max="2000"
                step="100"
                value={shortcutDuration}
                onChange={(e) => updateShortcutDuration(parseInt(e.target.value))}
                disabled={!isTauri}
                className="w-full h-2 bg-muted rounded-lg appearance-none cursor-pointer accent-primary"
              />
              <div className="flex justify-between text-xs text-muted-foreground">
                <span>200ms ({t('settings.voice.fast')})</span>
                <span>1000ms ({t('settings.voice.normal')})</span>
                <span>2000ms ({t('settings.voice.slow')})</span>
              </div>
            </div>
          )}

          {/* Test section for shortcut */}
          {isTauri && shortcutEnabled && (
            <div className="space-y-3 p-4 border rounded-lg">
              <Label className="text-base">
                {t('settings.voice.testShortcut')}
              </Label>
              <div className="flex items-center gap-4">
                <div className="flex-1">
                  {isShortcutRecording ? (
                    <div className="flex items-center gap-2 text-green-600 font-medium">
                      <span className="relative flex h-3 w-3">
                        <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-green-400 opacity-75"></span>
                        <span className="relative inline-flex rounded-full h-3 w-3 bg-green-500"></span>
                      </span>
                      {t('settings.voice.recording')}
                    </div>
                  ) : (
                    <div className="text-sm text-muted-foreground">
                      {triggerMode === 'doubleClick'
                        ? t('settings.voice.doubleClickInstruction', { key: shortcutKey })
                        : t('settings.voice.longPressInstruction', { key: shortcutKey })
                      }
                    </div>
                  )}
                </div>
              </div>
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  )
}
