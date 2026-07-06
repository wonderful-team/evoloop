import { Button } from "@evoloop/shared/components/ui/button"
import { Separator } from "@evoloop/shared/components/ui/separator"
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "@evoloop/shared/components/ui/tooltip"
import { cn } from "@evoloop/shared/lib/utils"
import axios from "axios"
import {
  BookOpen,
  Clock,
  Ear,
  Keyboard,
  Loader2,
  Mic,
  Paperclip,
  Send,
  Square,
  Terminal,
  Volume2,
  VolumeX,
  X,
} from "lucide-react"
import {
  forwardRef,
  memo,
  useCallback,
  useImperativeHandle,
  useMemo,
  useRef,
  useState,
} from "react"
import { useTranslation } from "react-i18next"
import { toast } from "sonner"
import { FilesService } from "@/client/sdk.gen"
import { SkillLibraryDialog } from "@/components/Learning/SkillLibraryDialog"
import {
  useTauriVoiceShortcut,
  useTauriVoiceShortcutSettings,
} from "@/hooks/useTauriVoiceShortcut"
import { useAutoSpeak, useTTS } from "@/hooks/useTTS"
import { useWakeWord, useWakeWordSettings } from "@/hooks/useWakeWord"
import { isTauri } from "@/lib/tauri"
import type { ActiveTaskInfo } from "@/stores/chat/types"
import { useChatStore } from "@/stores/chatStore"
import { FilePreview, type PickedFile } from "./FilePreview"
import { ModelSelector } from "./ModelSelector"
import { RecordingButton } from "./RecordingButton"
import {
  type ReferenceItem,
  ReferencePicker,
  type ReferencePickerHandle,
} from "./ReferencePicker"
import {
  VoiceRecorderButton,
  type VoiceRecorderButtonHandle,
} from "./VoiceRecorderButton"

function TaskPill({
  task,
  onClick,
}: {
  task: ActiveTaskInfo
  onClick: () => void
}) {
  const { t } = useTranslation()
  const isRunning = task.status === "running"
  const label =
    task.title.length > 30
      ? `${task.title.slice(0, 27)}${t("common.ellipsis")}`
      : task.title

  return (
    <button
      onClick={onClick}
      className="group flex items-center gap-1.5 px-2 py-0.5 rounded-md text-[11px] font-mono transition-all bg-background/80 border border-border/80 text-foreground shadow-2xs hover:border-primary hover:bg-muted/60 focus:outline-none focus-visible:ring-1 focus-visible:ring-primary shrink-0 cursor-pointer"
      title={t("chat.interface.openTerminal", { title: task.title })}
    >
      {isRunning ? (
        <Loader2 className="h-3 w-3 animate-spin text-green-500 flex-shrink-0" />
      ) : (
        <Clock className="h-3 w-3 text-amber-500 flex-shrink-0" />
      )}
      <span className="max-w-[120px] truncate">{label}</span>
    </button>
  )
}

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
  forwardRef<ChatInputAreaHandle, ChatInputAreaProps>(
    (
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
      },
      ref,
    ) => {
      const { t } = useTranslation()
      const isTerminalMode = useChatStore((s) => s.isTerminalMode)
      const setTerminalMode = useChatStore((s) => s.setTerminalMode)
      const activeTasks = useChatStore((s) => s.activeTasks)
      const tasks = useMemo(() => Object.values(activeTasks), [activeTasks])
      const [inputValue, setInputValue] = useState("")
      const [isUploading, setIsUploading] = useState(false)
      const [pickedFiles, setPickedFiles] = useState<PickedFile[]>([])
      const [isDragging, setIsDragging] = useState(false)

      const [showPicker, setShowPicker] = useState(false)
      const [searchQuery, setSearchQuery] = useState("")
      const [isSkillDialogOpen, setIsSkillDialogOpen] = useState(false)
      const textareaRef = useRef<HTMLTextAreaElement>(null)
      const pickerRef = useRef<ReferencePickerHandle>(null)

      // Helper to extract @query from cursor position
      const getSearchQueryAtCursor = (text: string, selectionStart: number) => {
        const textBeforeCursor = text.substring(0, selectionStart)
        const lastAtIndex = textBeforeCursor.lastIndexOf("@")
        if (lastAtIndex === -1) return null

        const queryText = textBeforeCursor.substring(lastAtIndex + 1)
        if (/\s/.test(queryText)) return null

        if (lastAtIndex > 0 && !/\s/.test(textBeforeCursor[lastAtIndex - 1])) {
          return null
        }
        return queryText
      }

      const handleTextareaChange = (val: string) => {
        setInputValue(val)
        const textarea = textareaRef.current
        if (textarea) {
          setTimeout(() => {
            const q = getSearchQueryAtCursor(val, textarea.selectionStart)
            if (q !== null) {
              setSearchQuery(q)
              setShowPicker(true)
            } else {
              setShowPicker(false)
            }
          }, 0)
        }
      }

      // History state
      const [history, setHistory] = useState<string[]>([])
      const [historyIndex, setHistoryIndex] = useState(-1) // -1: New Input, 0: Most recent history

      // Voice input mode
      const [inputMode, setInputMode] = useState<"text" | "voice">("text")
      const [autoTranscribe] = useState(true)
      const [isTranscribing, setIsTranscribing] = useState(false)
      const { autoSpeak, toggleAutoSpeak } = useAutoSpeak()
      const { stop: stopTTS, isSpeaking } = useTTS()

      // Wake word settings
      const { wakeWord, wakeWordEnabled } = useWakeWordSettings()
      const [showWakeWordIndicator, setShowWakeWordIndicator] = useState(false)

      // Tauri voice shortcut settings
      const { shortcutEnabled } = useTauriVoiceShortcutSettings()
      const [isRecordingFromShortcut, setIsRecordingFromShortcut] =
        useState(false)
      const voiceRecorderRef = useRef<VoiceRecorderButtonHandle>(null)

      const handleSend = () => {
        if ((!inputValue.trim() && pickedFiles.length === 0) || isSending)
          return

        // Pass raw input and files directly to store/parent
        // The store handles the optimistic display formatting and API payload construction
        onSend(inputValue, pickedFiles)

        // Request notification permission on first user gesture (if not already handled)
        if ("Notification" in window && Notification.permission === "default") {
          Notification.requestPermission()
        }

        // Add to history (Newest first)
        if (inputValue.trim()) {
          setHistory((prev) => [inputValue, ...prev])
        }
        setHistoryIndex(-1)

        // Clear state
        setInputValue("")
        setPickedFiles([])
      }

      const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
        if (showPicker && pickerRef.current) {
          if (e.key === "ArrowUp" || (e.ctrlKey && e.key === "p")) {
            e.preventDefault()
            pickerRef.current.moveUp()
            return
          }
          if (e.key === "ArrowDown" || (e.ctrlKey && e.key === "n")) {
            e.preventDefault()
            pickerRef.current.moveDown()
            return
          }
          if (e.key === "Tab") {
            e.preventDefault()
            if (e.shiftKey) {
              pickerRef.current.moveUp()
            } else {
              pickerRef.current.moveDown()
            }
            return
          }
          if (e.key === "Enter") {
            e.preventDefault()
            pickerRef.current.selectCurrent()
            return
          }
          if (e.key === "Escape") {
            e.preventDefault()
            setShowPicker(false)
            return
          }
        }

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
                  textareaRef.current.selectionStart =
                    textareaRef.current.value.length
                  textareaRef.current.selectionEnd =
                    textareaRef.current.value.length
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

        // 1. Create uploading files immediately for fast UI feedback
        const newUploadingFiles = Array.from(files).map((file) => {
          const isImage = file.type.startsWith("image/")
          const isAudio = file.type.startsWith("audio/")
          return {
            id: Math.random().toString(36).substring(2, 15),
            url: "", // empty url during upload
            name: file.name,
            type: (isImage
              ? "image"
              : isAudio
                ? "audio"
                : "file") as PickedFile["type"],
            status: "uploading" as const,
            _fileObj: file, // Keep reference for actual upload
          }
        })

        // Add to state immediately
        setPickedFiles((prev) => [...prev, ...newUploadingFiles])
        setIsUploading(true)

        try {
          const uploadPromises = newUploadingFiles.map(async (uploadFile) => {
            try {
              const res: any = await FilesService.uploadFile({
                projectId: projectId!,
                formData: { file: uploadFile._fileObj },
              })
              const url = res.url

              // Update success status and URL
              setPickedFiles((prev) =>
                prev.map((f) => {
                  if (f.id === uploadFile.id) {
                    return { ...f, url, status: "success" as const }
                  }
                  return f
                }),
              )
            } catch (error) {
              // Update error status
              setPickedFiles((prev) =>
                prev.map((f) => {
                  if (f.id === uploadFile.id) {
                    return { ...f, status: "error" as const }
                  }
                  return f
                }),
              )
              throw error // Re-throw to be caught by Promise.allSettled or catch block
            }
          })

          // Wait for all to finish, we don't use Promise.all to avoid failing the whole batch if one fails
          await Promise.allSettled(uploadPromises)
          // We could check if any failed and show a toast, but for now we just show a general success if we reached here
          // actually let's see if any failed
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

      const handlePaste = async (e: React.ClipboardEvent) => {
        if (e.clipboardData.files && e.clipboardData.files.length > 0) {
          if (disabled || (!currentProject && !isGlobalMode)) return

          const files = Array.from(e.clipboardData.files)
          if (files.length > 0) {
            // 只包含文件而不包含纯文本时，阻止默认行为
            if (!e.clipboardData.types.includes("text/plain")) {
              e.preventDefault()
            }
            await processFiles(files)
          }
        }
      }

      const handleSelectReference = (
        item: ReferenceItem,
        _insertText = false,
      ) => {
        // If user typed '@' to trigger the picker, strip the "@query" portion so it doesn't linger in text
        const textarea = textareaRef.current
        if (textarea) {
          const start = textarea.selectionStart
          const text = inputValue
          const lastAtIndex = text.lastIndexOf("@", start - 1)
          if (lastAtIndex !== -1) {
            const before = text.substring(0, lastAtIndex)
            const after = text.substring(start)

            // 保留文本形式的指代对象，让 LLM 能够结合上下文理解
            // 对于文件和目录，直接插入完整路径，避免同名文件带来的歧义
            const isFileOrDir =
              item.type === "directory" || item.type === "file"
            const replacementText = isFileOrDir
              ? `@${item.id} `
              : `@${item.name} `
            setInputValue(before + replacementText + after)

            setTimeout(() => {
              if (textarea) {
                const newCursor = lastAtIndex + replacementText.length
                textarea.selectionStart = newCursor
                textarea.selectionEnd = newCursor
              }
            }, 0)
          }
        }

        // Add to picked files (green reference badge)
        const newFile: PickedFile = {
          id: Math.random().toString(36).substring(2, 15),
          url: item.id,
          name: item.name,
          type:
            item.type === "directory"
              ? "directory"
              : item.type === "file"
                ? "file"
                : "reference",
        }
        if (item.type === "message") {
          newFile.type = "message"
        }

        setPickedFiles((prev) => {
          // Avoid duplicates
          if (prev.some((a) => a.url === newFile.url)) return prev
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
        if (inputMode !== "voice") {
          setInputMode("voice")
        }
        setShowWakeWordIndicator(true)
        // Auto-hide after 3 seconds
        setTimeout(() => setShowWakeWordIndicator(false), 3000)
        toast.success(t("chat.voice.wakeWordDetected"))
      }, [inputMode, t])

      const { isListening: isWakeWordListening } = useWakeWord({
        wakeWord,
        enabled: wakeWordEnabled && inputMode === "voice",
        onWake: handleWakeWordDetected,
      })

      // Tauri voice shortcut for voice recording
      const voiceShortcutHandlers = useMemo(
        () => ({
          onShortcutStart: () => {
            // 语音打断：如果正在播放语音，先停止
            if (isSpeaking) {
              stopTTS()
            }
            setIsRecordingFromShortcut(true)
            if (inputMode !== "voice") {
              setInputMode("voice")
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
          },
        }),
        [isSpeaking, stopTTS, inputMode],
      )

      useTauriVoiceShortcut({
        enabled: shortcutEnabled,
        ...voiceShortcutHandlers,
      })

      // Handle voice recording
      const handleVoiceRecorded = async ({
        blob,
        duration,
        waveform,
      }: {
        blob: Blob
        url: string
        path: string
        duration: number
        waveform: number[]
      }) => {
        if (!currentProject && !isGlobalMode) {
          toast.error(t("chat.voice.noProject"))
          return
        }

        try {
          const file = new File([blob], `voice_${Date.now()}.webm`, {
            type: "audio/webm",
          })

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
              type: "audio",
              metadata: { duration, waveform },
            }
            setPickedFiles((prev) => [...prev, newFile!])
            toast.success(t("chat.voice.sentSuccess"))
          }

          // Auto transcribe if enabled
          if (autoTranscribe) {
            setIsTranscribing(true)
            try {
              const formData = new FormData()
              formData.append("file", file)
              formData.append("language", "zh")

              const response = await axios.post(
                "/api/v1/audio/transcribe",
                formData,
                {
                  headers: { "Content-Type": "multipart/form-data" },
                },
              )

              if (response.data.text) {
                const transcript = response.data.text

                // 如果是快捷键录音，转写完成后直接发送
                if (isRecordingFromShortcut) {
                  onSend(transcript, newFile ? [newFile] : [])
                  setInputValue("")
                  setPickedFiles([]) // Clear for next message
                } else {
                  setInputValue((prev) =>
                    prev ? `${prev}\n${transcript}` : transcript,
                  )
                }
              }
            } catch (error) {
              console.error("Transcription failed:", error)
            } finally {
              setIsTranscribing(false)
            }
          }
        } catch (error: any) {
          toast.error(t("chat.voice.uploadFailed"))
          console.error(error)
        }
      }

      const toggleInputMode = () => {
        setInputMode((prev) => (prev === "text" ? "voice" : "text"))
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
        },
      }))

      return (
        <div className="w-full px-4 py-2 relative">
          {/* Reference Picker Popover - Hidden in global mode */}
          {showPicker && currentProject && !isGlobalMode && (
            <div className="absolute bottom-full left-0 right-0 z-50 px-4">
              {/* Click outside backdrop - Declared first to stay underneath */}
              <div
                className="fixed inset-0 z-40 bg-transparent"
                onClick={() => setShowPicker(false)}
              />
              {/* Picker card - Declared second with z-50 to overlay on top of the backdrop */}
              <ReferencePicker
                ref={pickerRef}
                projectId={currentProject.id!}
                searchQuery={searchQuery}
                onSelect={(item) => handleSelectReference(item, true)}
                onClose={() => setShowPicker(false)}
                className="relative z-50 origin-bottom"
              />
            </div>
          )}

          <div
            onDragOver={handleDragOver}
            onDragLeave={handleDragLeave}
            onDrop={handleDrop}
            className={cn(
              "bg-background rounded-2xl border transition-all ring-offset-0 overflow-hidden relative z-50",
              isDragging
                ? "border-primary border-2 border-dashed bg-primary/5 scale-[1.01]"
                : isTerminalMode
                  ? "border-[#7aa2f7]/30 focus-within:border-[#7aa2f7]/60 focus-within:ring-4 focus-within:ring-[#7aa2f7]/5"
                  : "border-input focus-within:border-primary/50 focus-within:ring-4 focus-within:ring-primary/5",
            )}
          >
            {isDragging && (
              <div className="absolute inset-0 z-[60] bg-primary/10 flex flex-col items-center justify-center gap-2 pointer-events-none">
                <Paperclip className="h-8 w-8 text-primary animate-bounce" />
                <span className="text-sm font-medium text-primary">
                  {t("chat.interface.dropToUpload")}
                </span>
              </div>
            )}
            {/* Top: File Preview */}
            <FilePreview
              pickedFiles={pickedFiles}
              onRemove={(id) =>
                setPickedFiles((prev) => prev.filter((a) => a.id !== id))
              }
              onClick={(file) => {
                if (file.type === "directory" || file.type === "file") {
                  window.dispatchEvent(
                    new CustomEvent("locate-file", {
                      detail: {
                        path: typeof file.url === "string" ? file.url : file.id,
                      },
                    }),
                  )
                }
              }}
            />

            {/* Wake Word Indicator */}
            {showWakeWordIndicator && (
              <div className="px-4 py-2 bg-green-500/10 border-b border-green-500/20 flex items-center gap-2">
                <Ear className="h-4 w-4 text-green-600 animate-pulse" />
                <span className="text-sm text-green-700 dark:text-green-400">
                  {t("chat.voice.wakeWordActive")}
                </span>
              </div>
            )}

            {/* Middle: Text Area or Voice Recorder */}
            {inputMode === "text" ? (
              <div className="px-2 py-2 flex items-center gap-2">
                {isTerminalMode && (
                  <span className="text-[#7aa2f7] font-mono font-bold select-none self-start">
                    {t("chat.terminal.promptSymbol")}
                  </span>
                )}
                <textarea
                  ref={textareaRef}
                  value={inputValue}
                  onChange={(e) => handleTextareaChange(e.target.value)}
                  onKeyDown={handleKeyDown}
                  onPaste={handlePaste}
                  placeholder={
                    isTerminalMode
                      ? t("chat.interface.terminalPlaceholder")
                      : disabled
                        ? t("chat.interface.inputDisabled")
                        : isGlobalMode
                          ? t("chat.interface.askGlobal")
                          : currentProject
                            ? t("chat.interface.askProject", {
                                project: currentProject.name,
                              })
                            : t("chat.interface.selectProject")
                  }
                  disabled={(!currentProject && !isGlobalMode) || disabled}
                  className="flex w-full bg-transparent border-none focus:ring-0 text-sm placeholder:text-muted-foreground resize-none focus-visible:outline-none disabled:cursor-not-allowed disabled:opacity-50 min-h-[36px] max-h-[300px]"
                  rows={1}
                  style={{ height: "auto", minHeight: "36px" }}
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
                {t("chat.voice.transcribing")}
              </div>
            )}

            {/* Bottom: Toolbar */}
            <div className="flex items-center justify-between border-t border-border/40 bg-muted/20 px-2 py-1 gap-2 overflow-hidden">
              {/* Left Group: Tools */}
              <div className="flex items-center gap-1.5 shrink-0 overflow-x-auto hide-scrollbar max-w-[70%]">
                {isTerminalMode ? (
                  <div className="flex items-center gap-1.5">
                    <button
                      onClick={() => setTerminalMode(false)}
                      className="flex items-center gap-1.5 px-2.5 py-1 rounded-md text-[11px] font-mono text-[#7aa2f7] bg-[#7aa2f7]/15 hover:bg-[#7aa2f7]/25 border border-[#7aa2f7]/30 font-bold transition-all select-none shrink-0 shadow-xs cursor-pointer group"
                      title={t("chat.interface.exitTerminal")}
                    >
                      <Terminal className="h-3.5 w-3.5" />
                      <span>{t("chat.interface.terminalMode")}</span>
                      <X className="h-3.5 w-3.5 ml-0.5 opacity-60 group-hover:opacity-100 transition-opacity" />
                    </button>
                    {tasks.map((task) => (
                      <TaskPill
                        key={task.task_id}
                        task={task}
                        onClick={() => setTerminalMode(true)}
                      />
                    ))}
                  </div>
                ) : (
                  <>
                    <ModelSelectorWrapper isSending={isSending} />

                    <div className="w-px h-6 bg-border mx-1" />

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
                          type: "skill",
                          metadata: {
                            skill_id: skill.id,
                            skill_name: skill.name,
                          },
                        }
                        setPickedFiles((prev) => [
                          ...prev.filter((a) => a.url !== skill.id),
                          newFile,
                        ])
                        setIsSkillDialogOpen(false)
                        toast.success(t("chat.skillAttached"))
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

                    <div className="flex items-center gap-1.5">
                      <Button
                        variant="ghost"
                        size="icon"
                        className="h-8 w-8 text-muted-foreground hover:text-foreground shrink-0 cursor-pointer"
                        title={t("chat.interface.enterTerminal")}
                        onClick={() => setTerminalMode(true)}
                      >
                        <Terminal size={16} />
                      </Button>
                      {tasks.map((task) => (
                        <TaskPill
                          key={task.task_id}
                          task={task}
                          onClick={() => setTerminalMode(true)}
                        />
                      ))}
                    </div>
                  </>
                )}
              </div>

              {/* Hint Text (Fluid Center) */}
              <div className="flex-1 min-w-0 px-2 pointer-events-none select-none text-[10px] text-muted-foreground/40 text-center truncate hidden md:block">
                {t("chat.interface.inputHint")}
              </div>

              {/* Right Group: Action */}
              <div className="flex items-center gap-1.5 shrink-0">
                {/* Wake word listening indicator */}
                {wakeWordEnabled && inputMode === "voice" && (
                  <TooltipProvider delayDuration={100}>
                    <Tooltip>
                      <TooltipTrigger asChild>
                        <div
                          className={cn(
                            "flex items-center gap-1.5 px-2 py-1 rounded-md text-xs",
                            isWakeWordListening
                              ? "bg-green-500/10 text-green-600"
                              : "bg-muted text-muted-foreground",
                          )}
                        >
                          <Ear
                            className={cn(
                              "h-3.5 w-3.5",
                              isWakeWordListening && "animate-pulse",
                            )}
                          />
                          <span className="hidden sm:inline">
                            {isWakeWordListening
                              ? t("chat.voice.listening")
                              : t("chat.voice.standby")}
                          </span>
                        </div>
                      </TooltipTrigger>
                      <TooltipContent side="top">
                        {t("chat.voice.wakeWordStatus", { word: wakeWord })}
                      </TooltipContent>
                    </Tooltip>
                  </TooltipProvider>
                )}

                {/* Voice and upload controls - only relevant for chat */}
                {!isTerminalMode && (
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

                    <Separator orientation="vertical" className="h-4 mx-1" />

                    <TooltipProvider delayDuration={100}>
                      <Tooltip>
                        <TooltipTrigger asChild>
                          <Button
                            variant={
                              inputMode === "voice" ? "secondary" : "ghost"
                            }
                            size="icon"
                            onClick={toggleInputMode}
                            disabled={isSending}
                            className="h-8 w-8"
                          >
                            {inputMode === "voice" ? (
                              <Keyboard className="h-4 w-4" />
                            ) : (
                              <Mic className="h-4 w-4" />
                            )}
                          </Button>
                        </TooltipTrigger>
                        <TooltipContent side="top">
                          {inputMode === "voice"
                            ? t("chat.voice.switchToText")
                            : t("chat.voice.switchToVoice")}
                        </TooltipContent>
                      </Tooltip>
                    </TooltipProvider>

                    <TooltipProvider delayDuration={100}>
                      <Tooltip>
                        <TooltipTrigger asChild>
                          <Button
                            variant={autoSpeak ? "secondary" : "ghost"}
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
                          {autoSpeak
                            ? t("chat.tts.autoSpeakOn")
                            : t("chat.tts.autoSpeakOff")}
                        </TooltipContent>
                      </Tooltip>
                    </TooltipProvider>

                    <div className="w-px h-6 bg-border mx-1" />
                  </>
                )}

                <Button
                  onClick={() => (isAgentWorking ? onStop() : handleSend())}
                  disabled={
                    inputMode === "voice" ||
                    (!inputValue.trim() &&
                      pickedFiles.length === 0 &&
                      !isAgentWorking) ||
                    isSending ||
                    (!currentProject && !isGlobalMode) ||
                    isUploading
                  }
                  size="sm"
                  className={`h-8 px-3 transition-all ${isAgentWorking ? "bg-red-500 hover:bg-red-600 text-white shadow-red-500/20 animate-pulse" : "shadow-primary/20"}`}
                >
                  {isAgentWorking || isStopPending ? (
                    <span className="flex items-center gap-2">
                      {isStopPending ? (
                        <Loader2 size={14} className="animate-spin" />
                      ) : (
                        <Square size={14} fill="currentColor" />
                      )}
                      <span className="text-xs font-medium">
                        {t("common.stop")}
                      </span>
                    </span>
                  ) : (
                    <span className="flex items-center gap-2">
                      <Send size={14} />
                      <span className="text-xs font-bold">
                        {t("common.send")}
                      </span>
                    </span>
                  )}
                </Button>
              </div>
            </div>
          </div>
        </div>
      )
    },
  ),
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
