import { BookOpen, Loader2, Paperclip, Send, Square, Mic, Keyboard, Volume2, VolumeX, Ear } from "lucide-react"
import { memo, useState, useRef, forwardRef, useImperativeHandle, useCallback, useMemo } from "react"
import { useTranslation } from "react-i18next"
import { toast } from "sonner"
import { FilesService } from "@/client/sdk.gen"
import { SkillLibraryDialog } from "@/components/Learning/SkillLibraryDialog"
import { Button } from "@evoloop/shared/components/ui/button"
import { cn } from "@evoloop/shared/lib/utils"
import { type Attachment, AttachmentPreview } from "./AttachmentPreview"
import { ReferencePicker, type ReferenceItem } from "./ReferencePicker"
import { RecordingButton } from "./RecordingButton"
import { VoiceRecorderButton } from "./VoiceRecorderButton"
import { ModelSelector } from "./ModelSelector"
import { useAutoSpeak, useTTS } from "@/hooks/useTTS"
import { useWakeWord, useWakeWordSettings } from "@/hooks/useWakeWord"
import { useTauriVoiceShortcut, useTauriVoiceShortcutSettings } from "@/hooks/useTauriVoiceShortcut"
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from "@evoloop/shared/components/ui/tooltip"
import { Separator } from "@evoloop/shared/components/ui/separator"
import { useChatStore } from "@/stores/chatStore"
import axios from "axios"

interface ChatInputAreaProps {
  onSend: (text: string, attachments?: any[]) => void
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
  addReference: (item: ReferenceItem) => void
  setInput: (text: string) => void
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
    const [attachments, setAttachments] = useState<Attachment[]>([])

    const [showPicker, setShowPicker] = useState(false)
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
    const [, setIsRecordingFromShortcut] = useState(false)

    const handleSend = () => {
      if ((!inputValue.trim() && attachments.length === 0) || isSending) return

      // Pass raw input and attachments directly to store/parent
      // The store handles the optimistic display formatting and API payload construction
      onSend(inputValue, attachments)

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
      setAttachments([])
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

    const handleUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
      const file = e.target.files?.[0]
      if (!file) return

      setIsUploading(true)
      try {
        if (!currentProject || !currentProject.id) {
          throw new Error("No project context")
        }
        const res: any = await FilesService.uploadFile({
          projectId: currentProject.id,
          formData: { file },
        })
        const url = res.url

        // Infer type
        const isImage = file.type.startsWith("image/")
        const isAudio = file.type.startsWith("audio/")
        const newAtt: Attachment = {
          id: crypto.randomUUID(),
          url: url,
          name: file.name,
          type: isImage ? "image" : isAudio ? "audio" : "file",
        }

        setAttachments((prev) => [...prev, newAtt])
        toast.success(t("chat.interface.uploadSuccess"))
      } catch (error: any) {
        toast.error(
          t("chat.interface.uploadError") +
          (error.message ? `: ${error.message}` : ""),
        )
        console.error(error)
      } finally {
        setIsUploading(false)
        e.target.value = ""
      }
    }

    const handleSelectReference = (item: ReferenceItem) => {
      // Insert text at cursor
      const textarea = textareaRef.current
      if (textarea) {
        const start = textarea.selectionStart
        const end = textarea.selectionEnd
        const text = inputValue
        const before = text.substring(0, start)
        const after = text.substring(end)

        // Only add space if needed
        const prefix = before.endsWith(" ") ? "" : " "
        const suffix = after.startsWith(" ") ? "" : " "

        const newText = before + prefix + `@${item.name}` + suffix + after
        setInputValue(newText)

        // Add to attachments
        const newAtt: Attachment = {
          id: crypto.randomUUID(),
          url: item.id,
          name: item.name,
          type: item.type === 'file' ? 'file' : 'reference',
        }
        if (item.type === 'message') {
          newAtt.type = 'message'
        }

        setAttachments(prev => {
          // Avoid duplicates
          if (prev.some(a => a.url === newAtt.url)) return prev
          return [...prev, newAtt]
        })

        // Restore focus
        setTimeout(() => {
          textarea.focus()
          // Update cursor position ???
        }, 0)
      }
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
      },
      onShortcutEnd: () => {
        setIsRecordingFromShortcut(false)
      }
    }), [isSpeaking, stopTTS, inputMode])

    useTauriVoiceShortcut({
      enabled: shortcutEnabled,
      ...voiceShortcutHandlers
    })

    // Handle voice recording
    const handleVoiceRecorded = async ({ blob, duration, waveform }: { blob: Blob; url: string; path: string; duration: number; waveform: number[] }) => {
      if (!currentProject) {
        toast.error(t('chat.voice.noProject', '请先选择项目'))
        return
      }

      try {
        const file = new File([blob], `voice_${Date.now()}.webm`, { type: 'audio/webm' })
        
        // Upload voice file
        const res: any = await FilesService.uploadFile({
          projectId: currentProject.id!,
          formData: { file },
        })
        const url = res.url

        // Add audio attachment
        const newAtt: Attachment = {
          id: crypto.randomUUID(),
          url: url,
          name: file.name,
          type: 'audio',
          metadata: { duration, waveform },
        }
        setAttachments((prev) => [...prev, newAtt])
        toast.success(t('chat.voice.sentSuccess', '语音已添加'))

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
              setInputValue(prev => prev ? `${prev}\n${transcript}` : transcript)
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
      addReference: (item: ReferenceItem) => {
        handleSelectReference(item)
      },
      setInput: (text: string) => {
        setInputValue(text)
      }
    }))

    return (
      <div
        className="shrink-0 p-4 pt-2 bg-background/95 backdrop-blur supports-[backdrop-filter]:bg-background/60"
        data-tour="chat-input"
      >
        <div className="w-full px-4 sm:px-6 lg:px-8 relative">
          {/* Reference Picker Popover - Hidden in global mode */}
          {showPicker && currentProject && !isGlobalMode && (
            <div className="absolute bottom-full left-0 mb-2 z-50">
              <ReferencePicker
                projectId={currentProject.id!}
                onSelect={handleSelectReference}
                onClose={() => setShowPicker(false)}
              />
              {/* Click outside backdrop */}
              <div
                className="fixed inset-0 z-40"
                onClick={() => setShowPicker(false)}
              />
            </div>
          )}

          <div className={cn(
            "bg-background/80 backdrop-blur-xl rounded-2xl border transition-all duration-300 overflow-hidden relative z-50 shadow-sm",
            "border-input hover:border-primary/30",
            "focus-within:border-primary/60 focus-within:shadow-[0_0_25px_-5px_rgba(var(--primary-rgb),0.2)] focus-within:ring-1 focus-within:ring-primary/20",
            isAgentWorking && "border-primary/40 shadow-[0_0_15px_-3px_rgba(var(--primary-rgb),0.1)]"
          )}>
            {/* Working Pulse Line (Top) */}
            <AnimatePresence>
              {isAgentWorking && (
                <motion.div 
                  initial={{ x: "-100%" }}
                  animate={{ x: "100%" }}
                  transition={{ repeat: Infinity, duration: 1.5, ease: "linear" }}
                  className="absolute top-0 left-0 h-[1.5px] w-full bg-gradient-to-r from-transparent via-primary to-transparent z-10"
                />
              )}
            </AnimatePresence>

            {/* Top: Attachment Preview */}
            <AttachmentPreview
              attachments={attachments}
              onRemove={(id) =>
                setAttachments((prev) => prev.filter((a) => a.id !== id))
              }
            />

            {/* Wake Word Indicator */}
            {showWakeWordIndicator && (
              <div className="px-4 py-2 bg-green-500/5 border-b border-green-500/10 flex items-center gap-2">
                <Ear className="h-4 w-4 text-green-500 animate-pulse" />
                <span className="text-[11px] font-bold text-green-600/80 uppercase tracking-tight">
                  {t('chat.voice.wakeWordActive', '唤醒词已激活，请说话...')}
                </span>
              </div>
            )}

            {/* Middle: Text Area or Voice Recorder */}
            {inputMode === 'text' ? (
              <div className="px-4 py-3">
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
                  className="flex w-full bg-transparent border-none focus:ring-0 text-sm placeholder:text-muted-foreground/50 resize-none focus-visible:outline-none disabled:cursor-not-allowed disabled:opacity-50 min-h-[52px] max-h-[300px] leading-relaxed scrollbar-none"
                  rows={1}
                  style={{ height: "auto", minHeight: "52px" }}
                  onInput={(e) => {
                    const target = e.target as HTMLTextAreaElement
                    target.style.height = "auto"
                    target.style.height = `${Math.min(target.scrollHeight, 500)}px`
                  }}
                />
              </div>
            ) : (
              <div className="px-3 py-4 flex items-center justify-center min-h-[100px]">
                <VoiceRecorderButton
                  onVoiceRecorded={handleVoiceRecorded}
                  disabled={isSending || !currentProject}
                />
              </div>
            )}

            {/* Transcribing indicator */}
            {isTranscribing && (
              <div className="px-4 py-1.5 flex items-center gap-2 text-[10px] font-bold text-primary/60 uppercase tracking-widest bg-primary/5 border-t border-primary/10">
                <Loader2 className="h-3 w-3 animate-spin" />
                {t('chat.voice.transcribing', '转文字中...')}
              </div>
            )}

            {/* Bottom: Toolbar */}
            <div className="relative flex items-center justify-between border-t border-border/10 bg-muted/30 p-2.5">
              {/* Hint Text (Centered) */}
              <div className="pointer-events-none absolute left-1/2 top-1/2 -translate-x-1/2 -translate-y-1/2 select-none text-[9px] font-black uppercase tracking-tighter text-muted-foreground/30 whitespace-nowrap hidden sm:block">
                {t("chat.interface.inputHint")}
              </div>

              {/* Left Group: Tools */}
              <div className="flex items-center gap-1.5">
                {activeThreadId && (
                  <>
                    <SkillLibraryDialog
                      threadId={activeThreadId}
                      projectId={currentProject?.id}
                      onSelectSkill={(skill) => {
                        const newAtt: Attachment = {
                          id: crypto.randomUUID(),
                          url: skill.id,
                          name: skill.name,
                          type: 'skill',
                          metadata: { skill_id: skill.id, skill_name: skill.name },
                        }
                        setAttachments(prev => [...prev, newAtt])
                        toast.success(t('chat.skillAttached', '技能已挂载'))
                      }}
                      trigger={
                        <Button
                          variant="ghost"
                          size="icon"
                          className="h-8 w-8 rounded-lg text-muted-foreground hover:text-primary hover:bg-primary/10 transition-all"
                          title={t("learning.skillLibrary")}
                        >
                          <BookOpen size={17} />
                        </Button>
                      }
                    />
                    <RecordingButton
                      threadId={activeThreadId}
                      enabled={true}
                    />
                  </>
                )}
                <div className="h-6 w-px bg-border/40 mx-0.5" />
                <ModelSelectorWrapper isSending={isSending} />
              </div>

              {/* Right Group: Action */}
              <div className="flex items-center gap-1.5">
                {/* Wake word listening indicator */}
                {wakeWordEnabled && inputMode === 'voice' && (
                  <div className={cn(
                    "flex items-center gap-1.5 px-2 py-1 rounded-lg text-[10px] font-bold uppercase tracking-tight",
                    isWakeWordListening 
                      ? "bg-emerald-500/10 text-emerald-600 border border-emerald-500/20" 
                      : "bg-muted/50 text-muted-foreground/50 border border-border/20"
                  )}>
                    <Ear className={cn("h-3 w-3", isWakeWordListening && "animate-pulse")} />
                    <span className="hidden sm:inline">
                      {isWakeWordListening ? t('chat.voice.listening') : t('chat.voice.standby')}
                    </span>
                  </div>
                )}

                {/* File upload */}
                {!isGlobalMode && (
                  <>
                    <input
                      type="file"
                      id="chat-file-upload"
                      className="hidden"
                      onChange={handleUpload}
                      disabled={!currentProject || isUploading}
                    />
                    <Button
                      variant="ghost"
                      size="icon"
                      className="h-8 w-8 rounded-lg text-muted-foreground hover:text-primary hover:bg-primary/10 transition-all"
                      onClick={() =>
                        document.getElementById("chat-file-upload")?.click()
                      }
                      disabled={isUploading || !currentProject}
                      title={t("chat.interface.uploadFile")}
                    >
                      {isUploading ? (
                        <Loader2 size={16} className="animate-spin" />
                      ) : (
                        <Paperclip size={16} />
                      )}
                    </Button>
                  </>
                )}

                {/* Voice mode toggle */}
                <Button
                  variant={inputMode === 'voice' ? 'secondary' : 'ghost'}
                  size="icon"
                  onClick={toggleInputMode}
                  disabled={isSending}
                  className={cn(
                    "h-8 w-8 rounded-lg transition-all",
                    inputMode === 'voice' ? "bg-primary/10 text-primary hover:bg-primary/20" : "text-muted-foreground hover:text-primary hover:bg-primary/10"
                  )}
                >
                  {inputMode === 'voice' ? (
                    <Keyboard className="h-4 w-4" />
                  ) : (
                    <Mic className="h-4 w-4" />
                  )}
                </Button>

                <Separator orientation="vertical" className="h-4 mx-0.5 opacity-40" />

                <Button
                  onClick={() => (isAgentWorking ? onStop() : handleSend())}
                  disabled={
                    inputMode === 'voice' ||
                    (!inputValue.trim() &&
                      attachments.length === 0 &&
                      !isAgentWorking) ||
                    isSending ||
                    (!currentProject && !isGlobalMode) ||
                    isUploading
                  }
                  size="sm"
                  className={cn(
                    "h-8 px-4 rounded-xl transition-all font-bold text-xs shadow-lg",
                    isAgentWorking 
                      ? "bg-red-500 hover:bg-red-600 text-white shadow-red-500/20" 
                      : "bg-primary hover:bg-primary/90 text-white shadow-primary/20"
                  )}
                >
                  {isAgentWorking || isStopPending ? (
                    <span className="flex items-center gap-2">
                      {isStopPending ? (
                        <Loader2 size={14} className="animate-spin" />
                      ) : (
                        <Square size={14} fill="currentColor" />
                      )}
                      <span>{t("common.stop")}</span>
                    </span>
                  ) : (
                    <span className="flex items-center gap-2">
                      <Send size={14} className={cn("transition-transform group-hover:translate-x-0.5 group-hover:-translate-y-0.5")} />
                      <span>{t("common.send")}</span>
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
