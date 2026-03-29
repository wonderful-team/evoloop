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
      toast.success(t('settings.voice.wakeWordDetected', '检测到唤醒词！'))
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
      toast.success(t('settings.voice.shortcutStarted', '快捷键激活，开始录音...'))
    },
    onShortcutEnd: () => {
      toast.info(t('settings.voice.shortcutEnded', '录音结束'))
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
    toast.success(t('settings.voice.wakeWordSaved', '唤醒词已保存'))
  }

  const handleToggleShortcut = async () => {
    if (!isTauri) {
      toast.error(t('settings.voice.tauriRequired', '快捷键功能需要在 Tauri 应用中运行'))
      return
    }
    await toggleShortcut()
    toast.success(shortcutEnabled 
      ? t('settings.voice.shortcutDisabled', '快捷键已禁用')
      : t('settings.voice.shortcutEnabled', '快捷键已启用')
    )
  }

  return (
    <div className="space-y-6">
      {/* Wake Word Section */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Mic className="h-5 w-5" />
            {t('settings.voice.wakeWordTitle', '唤醒词设置')}
          </CardTitle>
          <CardDescription>
            {t('settings.voice.wakeWordDesc', '设置语音唤醒词，说出唤醒词即可激活语音输入')}
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-6">
          {!isSupported && (
            <div className="flex items-start gap-2 p-3 bg-amber-500/10 rounded-lg text-sm text-amber-700 dark:text-amber-300">
              <AlertCircle className="h-4 w-4 shrink-0 mt-0.5" />
              <p>
                {t('settings.voice.notSupported', '您的浏览器不支持语音识别功能。请使用 Chrome、Edge 或 Safari 浏览器。')}
              </p>
            </div>
          )}

          {/* Enable toggle */}
          <div className="flex items-center justify-between p-4 bg-muted/50 rounded-lg">
            <div className="space-y-0.5">
              <Label className="text-base flex items-center gap-2">
                <Power className="h-4 w-4" />
                {t('settings.voice.enableWakeWord', '启用唤醒词')}
              </Label>
              <p className="text-sm text-muted-foreground">
                {t('settings.voice.enableWakeWordDesc', '持续监听麦克风，检测到唤醒词时自动开始录音')}
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
              {t('settings.voice.wakeWordLabel', '唤醒词')}
            </Label>
            <div className="flex gap-2">
              <input
                type="text"
                value={tempWakeWord}
                onChange={(e) => setTempWakeWord(e.target.value)}
                disabled={!isSupported}
                className="flex-1 px-3 py-2 bg-background border rounded-md text-sm focus:outline-none focus:ring-2 focus:ring-ring"
                placeholder={t('settings.voice.wakeWordPlaceholder', '例如：你好 Evo')}
              />
              <Button
                onClick={handleSaveWakeWord}
                disabled={!isSupported || tempWakeWord === wakeWord}
                variant="secondary"
              >
                {t('common.save', '保存')}
              </Button>
            </div>
            <p className="text-xs text-muted-foreground">
              {t('settings.voice.wakeWordHint', '建议使用 2-4 个字的短语，发音清晰易识别')}
            </p>
          </div>

          {/* Test section */}
          {isSupported && (
            <div className="space-y-3 p-4 border rounded-lg">
              <Label className="text-base">
                {t('settings.voice.testWakeWord', '测试唤醒词')}
              </Label>
              <div className="flex items-center gap-4">
                <Button
                  onClick={isWakeWordListening ? stopWakeWordListening : startWakeWordListening}
                  variant={isWakeWordListening ? 'destructive' : 'default'}
                >
                  {isWakeWordListening
                    ? t('settings.voice.stopListening', '停止监听')
                    : t('settings.voice.startListening', '开始监听')}
                </Button>
                <div className="flex-1">
                  {isWakeWordListening && (
                    <div className="flex items-center gap-2 text-sm">
                      <span className="relative flex h-3 w-3">
                        <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-red-400 opacity-75"></span>
                        <span className="relative inline-flex rounded-full h-3 w-3 bg-red-500"></span>
                      </span>
                      <span className="text-muted-foreground">
                        {t('settings.voice.listening', '正在监听...')}
                      </span>
                    </div>
                  )}
                  {isWakeWordDetected && (
                    <div className="text-green-600 font-medium">
                      ✓ {t('settings.voice.wakeWordDetected', '检测到唤醒词！')}
                    </div>
                  )}
                  {transcript && !isWakeWordDetected && (
                    <div className="text-sm text-muted-foreground">
                      {t('settings.voice.heard', '听到')}: "{transcript}"
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
            {t('settings.voice.shortcutTitle', '快捷键设置 (Tauri)')}
          </CardTitle>
          <CardDescription>
            {t('settings.voice.shortcutDesc', '设置双击或长按快捷键快速激活语音输入')}
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-6">
          {!isTauri && (
            <div className="flex items-start gap-2 p-3 bg-amber-500/10 rounded-lg text-sm text-amber-700 dark:text-amber-300">
              <AlertCircle className="h-4 w-4 shrink-0 mt-0.5" />
              <p>
                {t('settings.voice.tauriOnly', '此功能需要在 EvoLoop 桌面应用中运行，浏览器中无法使用系统级快捷键。')}
              </p>
            </div>
          )}

          {/* Enable toggle */}
          <div className="flex items-center justify-between p-4 bg-muted/50 rounded-lg">
            <div className="space-y-0.5">
              <Label className="text-base flex items-center gap-2">
                <Power className="h-4 w-4" />
                {t('settings.voice.enableShortcut', '启用快捷键')}
              </Label>
              <p className="text-sm text-muted-foreground">
                {triggerMode === 'doubleClick' 
                  ? t('settings.voice.enableDoubleClickDesc', '双击快捷键开始录音，单击结束')
                  : t('settings.voice.enableLongPressDesc', '长按快捷键开始录音，松手结束')
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
              {t('settings.voice.triggerMode', '触发方式')}
            </Label>
            <div className="flex gap-2">
              <Button
                variant={triggerMode === 'doubleClick' ? 'default' : 'outline'}
                onClick={() => updateTriggerMode('doubleClick')}
                disabled={!isTauri}
                className="flex-1"
              >
                <MousePointerClick className="h-4 w-4 mr-2" />
                {t('settings.voice.doubleClick', '双击')}
              </Button>
              <Button
                variant={triggerMode === 'longPress' ? 'default' : 'outline'}
                onClick={() => updateTriggerMode('longPress')}
                disabled={!isTauri}
                className="flex-1"
              >
                <Keyboard className="h-4 w-4 mr-2" />
                {t('settings.voice.longPress', '长按')}
              </Button>
            </div>
          </div>

          {/* Key selection */}
          <div className="space-y-3">
            <Label className="text-base">
              {t('settings.voice.shortcutKey', '快捷键')}
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
                ? t('settings.voice.doubleClickHint', '推荐：双击 Ctrl 是最方便的操作方式')
                : t('settings.voice.longPressHint', '推荐：长按 F1-F12 功能键或 Meta(Command/Windows) 键')
              }
            </p>
          </div>

          {/* Double click interval (only for double click mode) */}
          {triggerMode === 'doubleClick' && (
            <div className="space-y-3">
              <div className="flex justify-between">
                <Label className="text-base">
                  {t('settings.voice.doubleClickInterval', '双击间隔时间')}
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
                <span>100ms ({t('settings.voice.fast', '快')})</span>
                <span>500ms ({t('settings.voice.normal', '正常')})</span>
                <span>1000ms ({t('settings.voice.slow', '慢')})</span>
              </div>
            </div>
          )}

          {/* Long press duration (only for long press mode) */}
          {triggerMode === 'longPress' && (
            <div className="space-y-3">
              <div className="flex justify-between">
                <Label className="text-base">
                  {t('settings.voice.pressDuration', '长按持续时间')}
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
                <span>200ms ({t('settings.voice.fast', '快')})</span>
                <span>1000ms ({t('settings.voice.normal', '正常')})</span>
                <span>2000ms ({t('settings.voice.slow', '慢')})</span>
              </div>
            </div>
          )}

          {/* Test section for shortcut */}
          {isTauri && shortcutEnabled && (
            <div className="space-y-3 p-4 border rounded-lg">
              <Label className="text-base">
                {t('settings.voice.testShortcut', '测试快捷键')}
              </Label>
              <div className="flex items-center gap-4">
                <div className="flex-1">
                  {isShortcutRecording ? (
                    <div className="flex items-center gap-2 text-green-600 font-medium">
                      <span className="relative flex h-3 w-3">
                        <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-green-400 opacity-75"></span>
                        <span className="relative inline-flex rounded-full h-3 w-3 bg-green-500"></span>
                      </span>
                      {t('settings.voice.recording', '正在录音...')}
                    </div>
                  ) : (
                    <div className="text-sm text-muted-foreground">
                      {triggerMode === 'doubleClick'
                        ? t('settings.voice.doubleClickInstruction', '双击 {key} 键开始录音', { key: shortcutKey })
                        : t('settings.voice.longPressInstruction', '长按 {key} 键开始录音', { key: shortcutKey })
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
