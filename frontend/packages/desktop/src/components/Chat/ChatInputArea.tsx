import { BookOpen, Loader2, Paperclip, Send, Square, Mic, Keyboard, Volume2, VolumeX, Ear } from "lucide-react"
import { memo, useState, useRef, forwardRef, useImperativeHandle, useCallback, useMemo } from "react"
import { useTranslation } from "react-i18next"
import { toast } from "sonner"
import { FilesService } from "@/client/sdk.gen"
import { SkillLibraryDialog } from "@/components/Learning/SkillLibraryDialog"
import { Button } from "@evoloop/shared/components/ui/button"
import { cn } from "@evoloop/shared/lib/utils"
import { type PickedFile, FilePreview } from "./FilePreview"
import { ReferencePicker, type ReferenceItem } from "./ReferencePicker"
import { RecordingButton } from "./RecordingButton"
import { VoiceRecorderButton, type VoiceRecorderButtonHandle } from "./VoiceRecorderButton"
import { ModelSelector } from "./ModelSelector"
import { useAutoSpeak, useTTS } from "@/hooks/useTTS"
import { useWakeWord, useWakeWordSettings } from "@/hooks/useWakeWord"
import { useTauriVoiceShortcut, useTauriVoiceShortcutSettings } from "@/hooks/useTauriVoiceShortcut"
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from "@evoloop/shared/components/ui/tooltip"
import { Separator } from "@evoloop/shared/components/ui/separator"
import { useChatStore } from "@/stores/chatStore"
import { isTauri } from "@/lib/tauri"
import axios from "axios"

interface ChatInputAreaProps {
  onSend: (text: string, pickedFiles?: any[]) => void
  onStop: () => void
  isAgentWorking: boolean
  isSending: boolean
  isStopPending: boolean
  currentProject: { id?: number; name: string } | null | undefined
  activeThreadId?: string
  disabled?: boolean
  isGlobalMode?: boolean
}

export interface ChatInputAreaHandle {
  addReference: (item: ReferenceItem, insertText?: boolean) => void
  setInput: (text: string) => void
  focus: () => void
}

export const ChatInputArea = memo(
  forwardRef<ChatInputAreaHandle, ChatInputAreaProps>((
    {
      onSend,
      onStop,
      isAgentWorking,
      isSending,
      isStopPending,
      currentProject,
      activeThreadId,
      disabled,
      isGlobalMode,
    }, ref) => {
    const { t } = useTranslation()
    const [inputValue, setInputValue] = useState("")
    const [isUploading, setIsUploading] = useState(false)
    const [pickedFiles, setPickedFiles] = useState<PickedFile[]>([])
    const [isDragging, setIsDragging] = useState(false)

    const [showPicker, setShowPicker] = useState(false)
    const [isSkillDialogOpen, setIsSkillDialogOpen] = useState(false)
    const textareaRef = useRef<HTMLTextAreaElement>(null)

    // History state
    const [history, setHistory] = useState<string[]>([])
    const [historyIndex, setHistoryIndex] = useState(-1) // -1: New Input, 0: Most recent history

    // Voice input mode
    const [inputMode, setInputMode] = useState<'text' | 'voice'>('text')
    const [autoTranscribe] = useState(true)
    const [isTranscribing, setIsTranscribing] = useState(false)
    const { autoSpeak, toggleAutoSpeak } = useAutoSpeak()
    const { stop: stopTTS, isSpeaking } = useTTS()

    // Wake word settings
    const { wakeWord, wakeWordEnabled } = useWakeWordSettings()
    const [showWakeWordIndicator, setShowWakeWordIndicator] = useState(false)

    // Tauri voice shortcut settings
    const { shortcutEnabled } = useTauriVoiceShortcutSettings()
    const [isRecordingFromShortcut, setIsRecordingFromShortcut] = useState(false)
    const voiceRecorderRef = useRef<VoiceRecorderButtonHandle>(null)

    const handleSend = () => {
      if ((!inputValue.trim() && pickedFiles.length === 0) || isSending) return

      // Pass raw input and files directly to store/parent
      // The store handles the optimistic display formatting and API payload construction
      onSend(inputValue, pickedFiles)

      // Request notification permission on first user gesture (if not already handled)
      if ("Notification" in window && Notification.permission === "default") {
        Notification.requestPermission()
      }

      // Add to history (Newest first)
      if (inputValue.trim()) {
        setHistory(prev => [inputValue, ...prev])
      }
      setHistoryIndex(-1)

      // Clear state
      setInputValue("")
      setPickedFiles([])
    }

    const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
      if (e.key === "@") {
        setShowPicker(true)
      }

      if (e.key === "Enter" && !e.shiftKey) {
        if (showPicker) {
          e.preventDefault()
          handleSend()
        } else {
          e.preventDefault()
          handleSend()
        }
      }

      // History Traversal (Up/Down)
      // Only trigger if input is empty OR we are currently traversing history
      // This prevents interrupting multiline editing
      if ((inputValue === "" || historyIndex !== -1) && !e.shiftKey) {
        if (e.key === "ArrowUp") {
          e.preventDefault()
          const nextIndex = historyIndex + 1
          if (nextIndex < history.length) {
            setHistoryIndex(nextIndex)
            setInputValue(history[nextIndex])
            // Move cursor to end?
            setTimeout(() => {
              if (textareaRef.current) {
                textareaRef.current.selectionStart = textareaRef.current.value.length
                textareaRef.current.selectionEnd = textareaRef.current.value.length
              }
            }, 0)
          }
        } else if (e.key === "ArrowDown") {
          e.preventDefault()
          const nextIndex = historyIndex - 1
          if (nextIndex >= 0) {
            setHistoryIndex(nextIndex)
            setInputValue(history[nextIndex])
          } else {
            setHistoryIndex(-1)
            setInputValue("")
          }
        }
      }
    }

    const processFiles = async (files: FileList | File[]) => {
      if (files.length === 0) return

      const projectId = isGlobalMode ? 0 : currentProject?.id
      if (!isGlobalMode && !projectId) {
        toast.error(t("chat.interface.selectProject"))
        return
      }

      setIsUploading(true)
      try {
        const uploadPromises = Array.from(files).map(async (file) => {
          const res: any = await FilesService.uploadFile({
            projectId: projectId!,
            formData: { file },
          })
          const url = res.url

          // Infer type
          const isImage = file.type.startsWith("image/")
          const isAudio = file.type.startsWith("audio/")
          const newFile: PickedFile = {
            id: Math.random().toString(36).substring(2, 15),
            url: url,
            name: file.name,
            type: isImage ? "image" : isAudio ? "audio" : "file",
          }
          return newFile
        })

        const newFiles = await Promise.all(uploadPromises)
        setPickedFiles((prev) => [...prev, ...newFiles])
        toast.success(t("chat.interface.uploadSuccess"))
      } catch (error: any) {
        toast.error(
          t("chat.interface.uploadError") +
          (error.message ? `: ${error.message}` : ""),
        )
        console.error(error)
      } finally {
        setIsUploading(false)
      }
    }

    const handleUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
      if (e.target.files) {
        await processFiles(e.target.files)
        e.target.value = ""
      }
    }

    const handleDragOver = (e: React.DragEvent) => {
      e.preventDefault()
      e.stopPropagation()
      if (!disabled) {
        setIsDragging(true)
      }
    }

    const handleDragLeave = (e: React.DragEvent) => {
      e.preventDefault()
      e.stopPropagation()
      setIsDragging(false)
    }

    const handleDrop = async (e: React.DragEvent) => {
      e.preventDefault()
      e.stopPropagation()
      setIsDragging(false)

      if (disabled || (!currentProject && !isGlobalMode)) return

      if (e.dataTransfer.files && e.dataTransfer.files.length > 0) {
        await processFiles(e.dataTransfer.files)
      }
    }

    const handleSelectReference = (item: ReferenceItem, insertText = false) => {
      // If user typed '@' to trigger the picker, strip it so it doesn't linger in text
      const textarea = textareaRef.current
      if (textarea) {
        const start = textarea.selectionStart
        const end = textarea.selectionEnd
        const text = inputValue
        const lastAtIndex = text.lastIndexOf("@", start - 1)
        if (lastAtIndex !== -1 && text.substring(lastAtIndex, start).trim() === "@") {
          const before = text.substring(0, lastAtIndex)
          const after = text.substring(end)
          setInputValue(before + after)
          setTimeout(() => {
            if (textarea) {
              textarea.selectionStart = lastAtIndex
              textarea.selectionEnd = lastAtIndex
            }
          }, 0)
        }
      }

      // Add to picked files (green reference badge)
      const newFile: PickedFile = {
        id: Math.random().toString(36).substring(2, 15),
        url: item.id,
        name: item.name,
        type: item.type === 'file' ? 'file' : 'reference',
      }
      if (item.type === 'message') {
        newFile.type = 'message'
      }

      setPickedFiles(prev => {
        // Avoid duplicates
        if (prev.some(a => a.url === newFile.url)) return prev
        return [...prev, newFile]
      })

      // Restore focus to input area
      setTimeout(() => {
        textarea?.focus()
      }, 0)

      setShowPicker(false)
    }

    // Wake word detection
    const handleWakeWordDetected = useCallback(() => {
      if (inputMode !== 'voice') {
        setInputMode('voice')
      }
      setShowWakeWordIndicator(true)
      // Auto-hide after 3 seconds
      setTimeout(() => setShowWakeWordIndicator(false), 3000)
      toast.success(t('chat.voice.wakeWordDetected', '检测到唤醒词，开始录音'))
    }, [inputMode, t])

    const { isListening: isWakeWordListening } = useWakeWord({
      wakeWord,
      enabled: wakeWordEnabled && inputMode === 'voice',
      onWake: handleWakeWordDetected
    })

    // Tauri voice shortcut for voice recording
    const voiceShortcutHandlers = useMemo(() => ({
      onShortcutStart: () => {
        // 语音打断：如果正在播放语音，先停止
        if (isSpeaking) {
          stopTTS()
        }
        setIsRecordingFromShortcut(true)
        if (inputMode !== 'voice') {
          setInputMode('voice')
        }
        
        // 触发录音按钮开始录音
        setTimeout(() => {
          voiceRecorderRef.current?.start()
        }, 50)
      },
      onShortcutEnd: () => {
        voiceRecorderRef.current?.stop().then(() => {
           setIsRecordingFromShortcut(false)
        })
      }
    }), [isSpeaking, stopTTS, inputMode])

    useTauriVoiceShortcut({
      enabled: shortcutEnabled,
      ...voiceShortcutHandlers
    })

    // Handle voice recording
    const handleVoiceRecorded = async ({ blob, duration, waveform }: { blob: Blob; url: string; path: string; duration: number; waveform: number[] }) => {
      if (!currentProject && !isGlobalMode) {
        toast.error(t('chat.voice.noProject', '请先选择项目'))
        return
      }

      try {
        const file = new File([blob], `voice_${Date.now()}.webm`, { type: 'audio/webm' })
        
        let audioUrl = ""
        let newFile: PickedFile | null = null

        // If we have a project OR are in global mode, upload the file
        if (currentProject?.id || isGlobalMode) {
          const uploadProjectId = isGlobalMode ? 0 : currentProject!.id!
          const res: any = await FilesService.uploadFile({
            projectId: uploadProjectId,
            formData: { file },
          })
          audioUrl = res.url

          // Add audio file
          newFile = {
            id: Math.random().toString(36).substring(2, 15),
            url: audioUrl,
            name: file.name,
            type: 'audio',
            metadata: { duration, waveform },
          }
          setPickedFiles((prev) => [...prev, newFile!])
          toast.success(t('chat.voice.sentSuccess', '语音已添加'))
        }

        // Auto transcribe if enabled
        if (autoTranscribe) {
          setIsTranscribing(true)
          try {
            const formData = new FormData()
            formData.append('file', file)
            formData.append('language', 'zh')

            const response = await axios.post('/api/v1/audio/transcribe', formData, {
              headers: { 'Content-Type': 'multipart/form-data' },
            })

            if (response.data.text) {
              const transcript = response.data.text
              
              // 如果是快捷键录音，转写完成后直接发送
              if (isRecordingFromShortcut) {
                 onSend(transcript, newFile ? [newFile] : [])
                 setInputValue("")
                 setPickedFiles([]) // Clear for next message
              } else {
                 setInputValue(prev => prev ? `${prev}\n${transcript}` : transcript)
              }
            }
          } catch (error) {
            console.error('Transcription failed:', error)
          } finally {
            setIsTranscribing(false)
          }
        }
      } catch (error: any) {
        toast.error(t('chat.voice.uploadFailed', '语音上传失败'))
        console.error(error)
      }
    }

    const toggleInputMode = () => {
      setInputMode(prev => prev === 'text' ? 'voice' : 'text')
    }

    useImperativeHandle(ref, () => ({
      addReference: (item: ReferenceItem, insertText = false) => {
        handleSelectReference(item, insertText)
      },
      setInput: (text: string) => {
        setInputValue(text)
      },
      focus: () => {
        textareaRef.current?.focus()
      }
    }))

    return (
      <div
        className="shrink-0 p-2 pt-2 bg-background/95 backdrop-blur supports-[backdrop-filter]:bg-background/60"
        data-tour="chat-input"
      >
        <div className="w-full px-4 relative">
          {/* Reference Picker Popover - Hidden in global mode */}
          {showPicker && currentProject && !isGlobalMode && (
            <div className="absolute bottom-full left-0 mb-2 z-50">
              <ReferencePicker
                projectId={currentProject.id!}
                onSelect={(item) => handleSelectReference(item, true)}
                onClose={() => setShowPicker(false)}
              />
              {/* Click outside backdrop */}
              <div
                className="fixed inset-0 z-40"
                onClick={() => setShowPicker(false)}
              />
            </div>
          )}

          <div 
            onDragOver={handleDragOver}
            onDragLeave={handleDragLeave}
            onDrop={handleDrop}
            className={cn(
              "bg-background rounded-2xl border transition-all ring-offset-0 overflow-hidden relative z-50",
              isDragging ? "border-primary border-2 border-dashed bg-primary/5 scale-[1.01]" : "border-input focus-within:border-primary/50 focus-within:ring-4 focus-within:ring-primary/5"
            )}
          >
            {isDragging && (
              <div className="absolute inset-0 z-[60] bg-primary/10 flex flex-col items-center justify-center gap-2 pointer-events-none">
                <Paperclip className="h-8 w-8 text-primary animate-bounce" />
                <span className="text-sm font-medium text-primary">{t('chat.interface.dropToUpload', '松开上传文件')}</span>
              </div>
            )}
            {/* Top: File Preview */}
            <FilePreview
              pickedFiles={pickedFiles}
              onRemove={(id) =>
                setPickedFiles((prev) => prev.filter((a) => a.id !== id))
              }
            />

            {/* Wake Word Indicator */}
            {showWakeWordIndicator && (
              <div className="px-4 py-2 bg-green-500/10 border-b border-green-500/20 flex items-center gap-2">
                <Ear className="h-4 w-4 text-green-600 animate-pulse" />
                <span className="text-sm text-green-700 dark:text-green-400">
                  {t('chat.voice.wakeWordActive', '唤醒词已激活，请说话...')}
                </span>
              </div>
            )}

            {/* Middle: Text Area or Voice Recorder */}
            {inputMode === 'text' ? (
              <div className="px-3 py-2">
                <textarea
                  ref={textareaRef}
                  value={inputValue}
                  onChange={(e) => setInputValue(e.target.value)}
                  onKeyDown={handleKeyDown}
                  placeholder={
                    disabled
                      ? t("chat.interface.inputDisabled", "Please respond to the active request above...")
                      : isGlobalMode
                        ? t("chat.interface.askGlobal", "询问任何问题...")
                        : currentProject
                          ? t("chat.interface.askProject", {
                            project: currentProject.name,
                          })
                          : t("chat.interface.selectProject")
                  }
                  disabled={(!currentProject && !isGlobalMode) || disabled}
                  className="flex w-full bg-transparent border-none focus:ring-0 text-sm placeholder:text-muted-foreground resize-none focus-visible:outline-none disabled:cursor-not-allowed disabled:opacity-50 min-h-[50px] max-h-[300px]"
                  rows={1}
                  style={{ height: "auto", minHeight: "50px" }}
                  onInput={(e) => {
                    // Auto-grow hack
                    const target = e.target as HTMLTextAreaElement
                    target.style.height = "auto"
                    target.style.height = `${Math.min(target.scrollHeight, 500)}px`
                  }}
                />
              </div>
            ) : (
              <div className="px-3 py-2 flex items-center justify-center min-h-[80px]">
                <VoiceRecorderButton
                  ref={voiceRecorderRef}
                  onVoiceRecorded={handleVoiceRecorded}
                  disabled={isSending || isAgentWorking}
                />
              </div>
            )}

            {/* Transcribing indicator */}
            {isTranscribing && (
              <div className="px-4 py-1 flex items-center gap-2 text-xs text-muted-foreground">
                <Loader2 className="h-3 w-3 animate-spin" />
                {t('chat.voice.transcribing', '转文字中...')}
              </div>
            )}

            {/* Bottom: Toolbar */}
            <div className="flex items-center justify-between border-t border-border/40 bg-muted/20 p-2 gap-2 overflow-hidden">
              {/* Left Group: Tools */}
              <div className="flex items-center gap-1 shrink-0">
                <SkillLibraryDialog
                  open={isSkillDialogOpen}
                  onOpenChange={setIsSkillDialogOpen}
                  threadId={activeThreadId ?? ""}
                  projectId={currentProject?.id}
                  onSelectSkill={(skill) => {
                    // Attach skill as reference (allow multiple skills to be mounted)
                    const newFile: PickedFile = {
                      id: Math.random().toString(36).substring(2, 15),
                      url: skill.id,
                      name: skill.name,
                      type: 'skill',
                      metadata: { skill_id: skill.id, skill_name: skill.name },
                    }
                    setPickedFiles(prev => [...prev.filter(a => a.url !== skill.id), newFile])
                    setIsSkillDialogOpen(false)
                    toast.success(t('chat.skillAttached', '技能已挂载'))
                  }}
                  trigger={
                    <Button
                      variant="ghost"
                      size="icon"
                      className="h-8 w-8 text-muted-foreground hover:text-foreground"
                      title={t("learning.skillLibrary")}
                    >
                      <BookOpen size={16} />
                    </Button>
                  }
                />
                {isTauri() && (
                  <div className="h-8 flex items-center justify-center">
                    <RecordingButton
                      threadId={activeThreadId ?? ""}
                      enabled={true}
                    />
                  </div>
                )}
                {/* Model Selector */}
                <ModelSelectorWrapper isSending={isSending} />
              </div>

              {/* Hint Text (Fluid Center) */}
              <div className="flex-1 min-w-0 px-2 pointer-events-none select-none text-[10px] text-muted-foreground/40 text-center truncate hidden md:block">
                {t("chat.interface.inputHint")}
              </div>

              {/* Right Group: Action */}
              <div className="flex items-center gap-1.5 shrink-0">
                {/* Wake word listening indicator */}
                {wakeWordEnabled && inputMode === 'voice' && (
                  <TooltipProvider delayDuration={100}>
                    <Tooltip>
                      <TooltipTrigger asChild>
                        <div className={cn(
                          "flex items-center gap-1.5 px-2 py-1 rounded-md text-xs",
                          isWakeWordListening
                            ? "bg-green-500/10 text-green-600"
                            : "bg-muted text-muted-foreground"
                        )}>
                          <Ear className={cn("h-3.5 w-3.5", isWakeWordListening && "animate-pulse")} />
                          <span className="hidden sm:inline">
                            {isWakeWordListening ? t('chat.voice.listening', '监听中') : t('chat.voice.standby', '待机')}
                          </span>
                        </div>
                      </TooltipTrigger>
                      <TooltipContent side="top">
                        {t('chat.voice.wakeWordStatus', '唤醒词: "{{word}}"', { word: wakeWord })}
                      </TooltipContent>
                    </Tooltip>
                  </TooltipProvider>
                )}

                {/* File upload: 项目模式和全局模式均可上传 */}
                <>
                  <input
                    type="file"
                    id="chat-file-upload"
                    className="hidden"
                    onChange={handleUpload}
                    disabled={isUploading}
                  />
                  <Button
                    variant="ghost"
                    size="icon"
                    className="h-8 w-8 text-muted-foreground hover:text-foreground"
                    onClick={() =>
                      document.getElementById("chat-file-upload")?.click()
                    }
                    disabled={isUploading}
                    title={t("chat.interface.uploadFile")}
                  >
                    {isUploading ? (
                      <Loader2 size={16} className="animate-spin" />
                    ) : (
                      <Paperclip size={16} />
                    )}
                  </Button>
                </>

                {/* Voice controls */}
                <Separator orientation="vertical" className="h-4 mx-1" />
                {/* Voice mode toggle */}
                <TooltipProvider delayDuration={100}>
                  <Tooltip>
                    <TooltipTrigger asChild>
                      <Button
                        variant={inputMode === 'voice' ? 'secondary' : 'ghost'}
                        size="icon"
                        onClick={toggleInputMode}
                        disabled={isSending}
                        className="h-8 w-8"
                      >
                        {inputMode === 'voice' ? (
                          <Keyboard className="h-4 w-4" />
                        ) : (
                          <Mic className="h-4 w-4" />
                        )}
                      </Button>
                    </TooltipTrigger>
                    <TooltipContent side="top">
                      {inputMode === 'voice' ? t('chat.voice.switchToText') : t('chat.voice.switchToVoice')}
                    </TooltipContent>
                  </Tooltip>
                </TooltipProvider>
                {/* Auto Speak Toggle */}
                <TooltipProvider delayDuration={100}>
                  <Tooltip>
                    <TooltipTrigger asChild>
                      <Button
                        variant={autoSpeak ? 'secondary' : 'ghost'}
                        size="icon"
                        onClick={toggleAutoSpeak}
                        className="h-8 w-8"
                      >
                        {autoSpeak ? (
                          <Volume2 className="h-4 w-4 text-primary" />
                        ) : (
                          <VolumeX className="h-4 w-4 text-muted-foreground" />
                        )}
                      </Button>
                    </TooltipTrigger>
                    <TooltipContent side="top">
                      {autoSpeak ? t('chat.tts.autoSpeakOn') : t('chat.tts.autoSpeakOff')}
                    </TooltipContent>
                  </Tooltip>
                </TooltipProvider>

                <div className="w-px h-6 bg-border mx-1" />

                <Button
                  onClick={() => (isAgentWorking ? onStop() : handleSend())}
                  disabled={
                    inputMode === 'voice' ||
                    (!inputValue.trim() &&
                      pickedFiles.length === 0 &&
                      !isAgentWorking) ||
                    isSending ||
                    (!currentProject && !isGlobalMode) ||
                    isUploading
                  }
                  size="sm"
                  className={`h-8 px-3 rounded-lg transition-all ${isAgentWorking ? "bg-red-500 hover:bg-red-600 text-white shadow-red-500/20 shadow-lg animate-pulse" : "shadow-primary/20 shadow-md"}`}
                >
                  {isAgentWorking || isStopPending ? (
                    <span className="flex items-center gap-2">
                      {isStopPending ? (
                        <Loader2 size={14} className="animate-spin" />
                      ) : (
                        <Square size={14} fill="currentColor" />
                      )}
                      <span className="text-xs font-medium">
                        {t("common.stop", "Stop")}
                      </span>
                    </span>
                  ) : (
                    <span className="flex items-center gap-2">
                      <Send size={14} />
                      <span className="text-xs font-bold">
                        {t("common.send", "Send")}
                      </span>
                    </span>
                  )}
                </Button>
              </div>
            </div>
          </div>
        </div>
      </div>
    )
  })
)

// Wrapper component for ModelSelector that connects to chatStore
function ModelSelectorWrapper({ isSending }: { isSending: boolean }) {
  const selectedModel = useChatStore((state) => state.selectedModel)
  const setSelectedModel = useChatStore((state) => state.setSelectedModel)

  return (
    <ModelSelector
      value={selectedModel}
      onChange={setSelectedModel}
      disabled={isSending}
    />
  )
}

ChatInputArea.displayName = "ChatInputArea"
