import { Button } from "@evoloop/shared/components/ui/button"
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuLabel,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@evoloop/shared/components/ui/dropdown-menu"
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "@evoloop/shared/components/ui/tooltip"
import { cn } from "@evoloop/shared/lib/utils"
import {
  ArrowUp,
  BookOpen,
  ChevronDown,
  Ear,
  FileText,
  Film,
  Image as ImageIcon,
  MessageSquareQuote,
  Wand2,
  Loader2,
  MessageCircle,
  Mic,
  Paperclip,
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
  useEffect,
  useImperativeHandle,
  useRef,
  useState,
} from "react"
import { useTranslation } from "react-i18next"
import { toast } from "sonner"
import { FilesService } from "@/client/sdk.gen"
import { SkillLibraryDialog } from "@/components/Learning/SkillLibraryDialog"
import { useAutoSpeak } from "@/hooks/useTTS"
import { useWakeWord, useWakeWordSettings } from "@/hooks/useWakeWord"
import { isTauri, safeInvoke } from "@/lib/tauri"
import { useChatStore } from "@/stores/chatStore"
import { useHostContextStore } from "@/stores/hostContextStore"
import { useVoiceStore } from "@/stores/voiceStore"
import { FilePreview, type PickedFile } from "./FilePreview"
import { ModelSelector } from "./ModelSelector"
import { RecordingButton } from "./RecordingButton"
import {
  type ReferenceItem,
  ReferencePicker,
  type ReferencePickerHandle,
} from "./ReferencePicker"


// ── 输入区上下文模式（对话/生图/生视频/派任务）──────────────────
// 设计：模式只做三件事——切换参数组、切换话术 starter、切换 placeholder。
// 参数以文本后缀合成进消息（[生成参数] / [值守参数]），Agent prompt 直接消费。
type ChatMode = "chat" | "image" | "video"

interface ModeParamDef {
  label: string
  options: string[]
}

interface ModeDef {
  label: string
  icon: typeof ImageIcon
  params: ModeParamDef[]
  starter?: string
  placeholderKey: string
}

const CHAT_MODE_DEFS: Record<ChatMode, ModeDef> = {
  chat: {
    label: "对话",
    icon: MessageCircle,
    params: [],
    placeholderKey: "",
  },
  image: {
    label: "生图",
    icon: ImageIcon,
    params: [
      { label: "比例", options: ["1:1", "3:4", "4:3", "16:9"] },
      { label: "风格", options: ["写实", "插画", "国风", "赛博朋克"] },
      { label: "张数", options: ["1", "2", "4"] },
    ],
    starter: "画一只…",
    placeholderKey: "chat.interface.imagePlaceholder",
  },
  video: {
    label: "生视频",
    icon: Film,
    params: [
      { label: "比例", options: ["16:9", "9:16", "1:1"] },
      { label: "风格", options: ["写实", "动画", "电影感"] },
      { label: "时长", options: ["5s", "10s"] },
    ],
    starter: "生成一段视频：…",
    placeholderKey: "chat.interface.videoPlaceholder",
  },
}

// ── 常用话术模板（分类组织；v2 迁移至项目侧能力包配置）────────
interface PhraseTemplate {
  label: string
  text: string
}

interface PhraseCategory {
  category: string
  items: PhraseTemplate[]
}

const PHRASE_TEMPLATES: PhraseCategory[] = [
  {
    category: "值守巡检",
    items: [
      {
        label: "订单巡检",
        text: "请对商城进行订单巡检：检查是否有待发货、待付款或异常订单，有则直接处理并回复处理结果，无则回复「本次订单巡检无待办」。",
      },
      {
        label: "售后巡检",
        text: "请对商城进行售后巡检：检查是否有待处理的退款、退货、换货工单，有则直接处理并回复处理结果，无则回复「本次售后巡检无待办」。",
      },
      {
        label: "库存巡检",
        text: "请对商城进行库存巡检：检查是否有低库存预警、缺货商品或库存异常，有则直接处理并回复处理结果，无则回复「本次库存巡检无待办」。",
      },
      {
        label: "会员巡检",
        text: "请对商城进行会员巡检：检查是否有待处理的会员投诉、等级/积分异常，有则直接处理并回复处理结果；会员提现不纳入自动处理，仅汇报待办数量，无则回复「本次会员巡检无待办」。",
      },
      {
        label: "营销巡检",
        text: "请对商城进行营销巡检：检查是否有即将到期、异常或待生效的促销活动/优惠券/满减规则，有则直接处理并回复处理结果，无则回复「本次营销巡检无待办」。",
      },
      {
        label: "资金巡检",
        text: "请对商城进行资金巡检：检查是否有待处理的结算异常、提现审批、对账差异或资金风险，有则直接处理并回复处理结果，无则回复「本次资金巡检无待办」。",
      },
    ],
  },
  {
    category: "任务委托",
    items: [
      {
        label: "建值守任务",
        text: "请帮我把这件事建成值守任务：\n· 要做的事：\n· 执行频率（可选，如每天 09:00 / 每 30 分钟）：\n· 需要特别注意的风险点（可选）：",
      },
      {
        label: "建一次性任务",
        text: "请帮我把这件事建成一个待办任务：\n· 要做的事：\n· 完成标准：",
      },
    ],
  },
]

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
  className?: string
  hideTerminal?: boolean
  hideVoice?: boolean
  hideAutoSpeak?: boolean
  hideRecording?: boolean
  contextSlot?: React.ReactNode
  cardClassName?: string
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
        className,
        hideTerminal = false,
        hideVoice = false,
        hideAutoSpeak = false,
        hideRecording = false,
        contextSlot,
        cardClassName,
      },
      ref,
    ) => {
      const { t } = useTranslation()
      const isTerminalMode = useChatStore((s) => s.isTerminalMode)
      const setTerminalMode = useChatStore((s) => s.setTerminalMode)
      // 宿主内嵌：隐藏技能库/终端等桌面工具按钮，保留模型选择与输入
      const isEmbedded = useHostContextStore((s) => s.connected)
      const [inputValue, setInputValue] = useState("")
      const [chatMode, setChatMode] = useState<ChatMode>("chat")
      const [activeParams, setActiveParams] = useState<Record<string, string>>({})

      // 切换模式：清参数；非对话模式自动填 starter（仅在输入框为空时，不打扰已输入内容）
      function switchChatMode(mode: ChatMode) {
        if (mode === chatMode) return
        setChatMode(mode)
        setActiveParams({})
        if (mode !== "chat") setTerminalMode(false)
        const starter = CHAT_MODE_DEFS[mode].starter
        if (starter && !inputValue.trim()) setInputValue(starter)
      }

      function setParam(label: string, value: string | null) {
        setActiveParams((prev) => {
          const next = { ...prev }
          if (value === null) delete next[label]
          else next[label] = value
          return next
        })
      }

      // 发送合成：激活参数 → 结构化后缀（Agent prompt 直接消费）
      function composeOutgoingText(raw: string): string {
        if (chatMode === "chat") return raw
        const modeDef = CHAT_MODE_DEFS[chatMode]
        if (chatMode === "image" || chatMode === "video") {
          const parts = [`类型=${chatMode === "image" ? "图片" : "视频"}`]
          for (const p of modeDef.params) {
            const v = activeParams[p.label]
            if (v) parts.push(`${p.label}=${v}`)
          }
          const suffix = `[生成参数] ${parts.join(" ")}`
          return raw.trim() ? `${raw.trim()}\n${suffix}` : suffix
        }
        return raw
      }
      const [isUploading, setIsUploading] = useState(false)
      const [pickedFiles, setPickedFiles] = useState<PickedFile[]>([])
      const [isDragging, setIsDragging] = useState(false)

      const [showPicker, setShowPicker] = useState(false)
      const [searchQuery, setSearchQuery] = useState("")
      const [isSkillDialogOpen, setIsSkillDialogOpen] = useState(false)
      const textareaRef = useRef<HTMLTextAreaElement>(null)

      // 自动增高：随 inputValue 变化（含话术模板/草稿的程序化填入）
      useEffect(() => {
        const textarea = textareaRef.current
        if (!textarea) return
        textarea.style.height = "auto"
        textarea.style.height = `${Math.min(textarea.scrollHeight, 500)}px`
      }, [inputValue])

      // 值守工作台"派个任务"预填草稿：挂载即消费（一次性），并聚焦输入框
      useEffect(() => {
        const draft = useChatStore.getState().pendingTaskDraft
        if (draft) {
          setInputValue(draft)
          useChatStore.getState().setPendingTaskDraft(null)
          requestAnimationFrame(() => textareaRef.current?.focus())
        }
        // eslint-disable-next-line react-hooks/exhaustive-deps
      }, [])
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

      // Voice mode: off | dictation | dialogue (shared globally via voiceStore)
      const voiceMode = useVoiceStore((s) => s.voiceMode)
      const setVoiceMode = useVoiceStore((s) => s.setVoiceMode)
      const { autoSpeak, toggleAutoSpeak } = useAutoSpeak()
      const voiceState = useVoiceStore((s) => s.voiceState)

      // Wake word settings
      const { wakeWord, wakeWordEnabled } = useWakeWordSettings()
      const [showWakeWordIndicator, setShowWakeWordIndicator] = useState(false)

      const handleSend = () => {
        if ((!inputValue.trim() && pickedFiles.length === 0) || isSending)
          return
        // 审计修复：上传未完成（url 为空）的附件不得随消息发出
        if (isUploading) {
          toast.info(t("chat.interface.uploadInProgress", { defaultValue: "附件上传中，请稍候…" }))
          return
        }

        // Pass raw input and files directly to store/parent
        // The store handles the optimistic display formatting and API payload construction
        onSend(composeOutgoingText(inputValue), pickedFiles)

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
          e.preventDefault()
          handleSend()
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

        const projectId = isGlobalMode || !currentProject?.id ? 0 : currentProject.id

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

        if (disabled) return

        if (e.dataTransfer.files && e.dataTransfer.files.length > 0) {
          await processFiles(e.dataTransfer.files)
        }
      }

      const handlePaste = async (e: React.ClipboardEvent) => {
        if (e.clipboardData.files && e.clipboardData.files.length > 0) {
          if (disabled) return

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

      // Wake word detected — stop listener, let useVoiceEvents start session
      const handleWakeWordDetected = useCallback(() => {
        setShowWakeWordIndicator(true)
        setTimeout(() => setShowWakeWordIndicator(false), 3000)
        if (!isTauri()) return
        safeInvoke("stop_wake_word_listener").catch(() => {})
        setVoiceMode("dialogue")
      }, [])

      useWakeWord({
        wakeWord,
        enabled: wakeWordEnabled,
        onWake: handleWakeWordDetected,
      })

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
        <div className={cn("w-full px-4 py-2 relative", className)}>
          {/* @ Reference Picker Popover */}
          {showPicker && currentProject && !isGlobalMode && (
            <div className="absolute bottom-full left-0 right-0 z-50 px-4">
              <button
                type="button"
                aria-label={t("common.close")}
                tabIndex={-1}
                className="fixed inset-0 z-40 bg-transparent cursor-default"
                onClick={() => setShowPicker(false)}
              />
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

          {/* ── 输入卡片 ── */}
          <div
            role="region"
            aria-label={t("chat.interface.uploadFile")}
            onDragOver={handleDragOver}
            onDragLeave={handleDragLeave}
            onDrop={handleDrop}
            className={cn(
              "rounded-2xl border bg-[var(--panel,#ffffff)] dark:bg-[#14151a] shadow-sm transition-all overflow-hidden relative z-50",
              isDragging
                ? "border-primary border-dashed bg-primary/5 scale-[1.01]"
                : isTerminalMode
                  ? "border-signal-blue/40 focus-within:border-signal-blue/60 focus-within:ring-4 focus-within:ring-signal-blue/10"
                  : "border-border focus-within:border-primary/50 focus-within:shadow-md focus-within:ring-4 focus-within:ring-primary/5",
              cardClassName,
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

            {/* ── 上下文行：外部插槽 + 附件 + 模式芯片 + 参数 pills + 终端芯片 ── */}
            {(contextSlot ||
              pickedFiles.length > 0 ||
              (!hideTerminal && isTerminalMode) ||
              (!hideVoice && showWakeWordIndicator) ||
              chatMode !== "chat") && (
              <div className="px-3 pt-2.5 flex flex-wrap items-center gap-1.5">
                {contextSlot}
                {showWakeWordIndicator && (
                  <div className="flex items-center gap-1 px-2 py-0.5 rounded-full text-[11px] text-success bg-success/10 border border-success/20 select-none">
                    <Ear className="h-3 w-3 animate-pulse" />
                    <span>{t("chat.voice.wakeWordActive")}</span>
                  </div>
                )}
                {isTerminalMode && (
                  <button
                    type="button"
                    onClick={() => setTerminalMode(false)}
                    className="flex items-center gap-1 px-2 py-0.5 rounded-full text-[11px] font-mono text-signal-blue bg-signal-blue/10 border border-signal-blue/30 select-none cursor-pointer hover:bg-signal-blue/20 transition-colors"
                    title={t("chat.interface.exitTerminal")}
                  >
                    <Terminal className="h-3 w-3" />
                    <span>{t("chat.interface.terminalMode")}</span>
                    <X className="h-3 w-3 opacity-60" />
                  </button>
                )}
                {chatMode !== "chat" && !isTerminalMode && (
                  <button
                    type="button"
                    onClick={() => switchChatMode("chat")}
                    className="flex items-center gap-1 px-2 py-0.5 rounded-full text-[11px] font-medium text-primary bg-primary/10 border border-primary/30 select-none cursor-pointer hover:bg-primary/20 transition-colors"
                    title={t("chat.interface.exitMode", {
                      defaultValue: "退出该模式",
                    })}
                  >
                    <Wand2 className="h-3 w-3" />
                    <span>{CHAT_MODE_DEFS[chatMode].label}</span>
                    <X className="h-3 w-3 opacity-60" />
                  </button>
                )}
                {chatMode !== "chat" &&
                  !isTerminalMode &&
                  CHAT_MODE_DEFS[chatMode].params.map((p) => {
                    const val = activeParams[p.label]
                    return (
                      <DropdownMenu key={p.label}>
                        <DropdownMenuTrigger asChild>
                          <button
                            type="button"
                            className={cn(
                              "flex items-center gap-1 px-2 py-0.5 rounded-full text-[11px] border select-none cursor-pointer transition-colors",
                              val
                                ? "bg-muted border-border text-foreground font-medium"
                                : "bg-background border-dashed border-border text-muted-foreground hover:border-primary/40 hover:text-foreground",
                            )}
                          >
                            {val ? (
                              <>
                                <span className="text-muted-foreground/70">
                                  {p.label}
                                </span>
                                <span>{val}</span>
                                <X className="h-2.5 w-2.5 opacity-50" />
                              </>
                            ) : (
                              <>
                                {p.label}
                                <ChevronDown className="h-2.5 w-2.5 opacity-50" />
                              </>
                            )}
                          </button>
                        </DropdownMenuTrigger>
                        <DropdownMenuContent align="start">
                          {p.options.map((o) => (
                            <DropdownMenuItem
                              key={o}
                              onClick={() => setParam(p.label, o)}
                              className={
                                val === o ? "text-primary font-medium" : ""
                              }
                            >
                              {o}
                              {val === o && (
                                <span className="ml-auto text-primary">✓</span>
                              )}
                            </DropdownMenuItem>
                          ))}
                          {val && (
                            <DropdownMenuItem
                              onClick={() => setParam(p.label, null)}
                            >
                              清除
                            </DropdownMenuItem>
                          )}
                        </DropdownMenuContent>
                      </DropdownMenu>
                    )
                  })}
                <FilePreview
                  pickedFiles={pickedFiles}
                  onRemove={(id) =>
                    setPickedFiles((prev) =>
                      prev.filter((a) => a.id !== id),
                    )
                  }
                  onClick={(file) => {
                    if (file.type === "directory" || file.type === "file") {
                      window.dispatchEvent(
                        new CustomEvent("locate-file", {
                          detail: {
                            path:
                              typeof file.url === "string" ? file.url : file.id,
                          },
                        }),
                      )
                    }
                  }}
                />
              </div>
            )}

            {/* ── 文本区 ── */}
            <div className="px-3.5 pt-2.5 pb-1 flex items-start gap-2">
              {isTerminalMode && (
                <span className="text-signal-blue font-mono font-bold select-none self-start pt-1.5">
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
                    ? t("chat.terminal.promptPlaceholder", {
                        defaultValue: "输入命令，Enter 直接执行…",
                      })
                    : chatMode !== "chat"
                      ? t(CHAT_MODE_DEFS[chatMode].placeholderKey, {
                          defaultValue:
                            chatMode === "image"
                              ? "描述你想要的画面…"
                              : chatMode === "video"
                                ? "描述要生成的视频…"
                                : "把要做的事交给 Agent…",
                        })
                      : disabled
                        ? t("chat.interface.inputDisabled")
                        : isGlobalMode || !currentProject
                          ? t("chat.interface.askGlobal")
                          : t("chat.interface.askProject", {
                              project: currentProject.name,
                            })
                }
                disabled={disabled}
                className="flex w-full bg-transparent border-none focus:ring-0 text-sm placeholder:text-muted-foreground/60 resize-none focus-visible:outline-none disabled:cursor-not-allowed disabled:opacity-50 min-h-[44px] max-h-[300px] py-1"
                rows={1}
                style={{ height: "auto", minHeight: "44px" }}
              />
            </div>

            {/* ── 工具条 ── */}
            <div className="px-1 pb-1 pt-0.5 flex items-center gap-1 flex-nowrap">
              {/* 左组：附件 / 技能 / 录制 / 创作 / 终端 / 语音 / 自动朗读 */}
              <div className="flex items-center gap-0.5 min-w-0 overflow-x-auto hide-scrollbar">
                <input
                  type="file"
                  id="chat-file-upload"
                  className="hidden"
                  multiple
                  onChange={handleUpload}
                  disabled={isUploading}
                />
                <TooltipProvider delayDuration={100}>
                  <Tooltip>
                    <TooltipTrigger asChild>
                      <Button
                        variant="ghost"
                        size="icon"
                        className="h-8 w-8 text-muted-foreground hover:text-foreground"
                        onClick={() =>
                          document.getElementById("chat-file-upload")?.click()
                        }
                        disabled={isUploading}
                      >
                        {isUploading ? (
                          <Loader2 size={16} className="animate-spin" />
                        ) : (
                          <Paperclip size={16} />
                        )}
                      </Button>
                    </TooltipTrigger>
                    <TooltipContent side="top">
                      {t("chat.interface.uploadFile")}
                    </TooltipContent>
                  </Tooltip>
                </TooltipProvider>

                {!isTerminalMode && (
                  <>
                    {!isEmbedded && (
                      <SkillLibraryDialog
                        open={isSkillDialogOpen}
                        onOpenChange={setIsSkillDialogOpen}
                        threadId={activeThreadId ?? ""}
                        projectId={currentProject?.id}
                        onSelectSkill={(skill) => {
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
                            className="h-8 px-2 gap-1 text-[11px] text-muted-foreground hover:text-foreground shrink-0"
                            title={t("learning.skillLibrary")}
                          >
                            <BookOpen size={14} />
                            <span className="hidden lg:inline">
                              {t("chat.interface.skillLabel", {
                                defaultValue: "技能",
                              })}
                            </span>
                          </Button>
                        }
                      />
                    )}

                    {isTauri() && !isEmbedded && !hideRecording && (
                      <div className="hidden lg:flex items-center justify-center">
                        <RecordingButton
                          threadId={activeThreadId ?? ""}
                          enabled={true}
                          withText={true}
                        />
                      </div>
                    )}

                    {/* 创作：模式下拉（生图 / 生视频 / 派任务） */}
                    {!isEmbedded && (
                      <DropdownMenu>
                        <DropdownMenuTrigger asChild>
                          <Button
                            variant="ghost"
                            className={cn(
                              "h-8 px-2 gap-1 text-[11px] shrink-0",
                              chatMode !== "chat"
                                ? "text-primary bg-primary/10 font-medium"
                                : "text-muted-foreground hover:text-foreground",
                            )}
                            title={t("chat.interface.creativeLabel", {
                              defaultValue: "创作模式",
                            })}
                          >
                            <Wand2 size={14} />
                            <span className="hidden lg:inline">
                              {chatMode !== "chat"
                                ? CHAT_MODE_DEFS[chatMode].label
                                : t("chat.interface.creativeLabel", {
                                    defaultValue: "创作",
                                  })}
                            </span>
                            <ChevronDown size={12} className="opacity-60" />
                          </Button>
                        </DropdownMenuTrigger>
                        <DropdownMenuContent align="start">
                          {(
                            ["image", "video"] as ChatMode[]
                          ).map((m) => (
                            <DropdownMenuItem
                              key={m}
                              onClick={() => switchChatMode(m)}
                              className={
                                chatMode === m ? "text-primary font-medium" : ""
                              }
                            >
                              {(() => {
                                const Def = CHAT_MODE_DEFS[m]
                                const DefIcon = Def.icon
                                return (
                                  <>
                                    <DefIcon size={14} className="mr-2" />
                                    {Def.label}
                                    {chatMode === m && (
                                      <span className="ml-auto text-primary">
                                        ✓
                                      </span>
                                    )}
                                  </>
                                )
                              })()}
                            </DropdownMenuItem>
                          ))}
                          {chatMode !== "chat" && (
                            <>
                              <DropdownMenuSeparator />
                              <DropdownMenuItem
                                onClick={() => switchChatMode("chat")}
                              >
                                <X size={14} className="mr-2" />
                                {t("chat.interface.exitMode", {
                                  defaultValue: "退出创作模式",
                                })}
                              </DropdownMenuItem>
                            </>
                          )}
                        </DropdownMenuContent>
                      </DropdownMenu>
                    )}

                    {!isEmbedded && (
                      <DropdownMenu>
                        <DropdownMenuTrigger asChild>
                          <Button
                            variant="ghost"
                            className="h-8 px-2 gap-1 text-[11px] text-muted-foreground hover:text-foreground shrink-0 cursor-pointer"
                            title={t("chat.interface.phraseLabel", {
                              defaultValue: "常用话术",
                            })}
                          >
                            <MessageSquareQuote size={14} />
                            <span className="hidden lg:inline">
                              {t("chat.interface.phraseLabel", {
                                defaultValue: "话术",
                              })}
                            </span>
                            <ChevronDown size={12} className="opacity-60" />
                          </Button>
                        </DropdownMenuTrigger>
                        <DropdownMenuContent align="start" className="max-h-[360px] overflow-y-auto">
                          {PHRASE_TEMPLATES.map((group) => (
                            <div key={group.category}>
                              <DropdownMenuLabel className="text-[10px] text-muted-foreground">
                                {group.category}
                              </DropdownMenuLabel>
                              {group.items.map((tpl) => (
                                <DropdownMenuItem
                                  key={tpl.label}
                                  onClick={() =>
                                    setInputValue((prev) =>
                                      prev.trim()
                                        ? `${prev.trim()}\n\n${tpl.text}`
                                        : tpl.text,
                                    )
                                  }
                                  className="text-xs"
                                >
                                  {tpl.label}
                                </DropdownMenuItem>
                              ))}
                              <DropdownMenuSeparator />
                            </div>
                          ))}
                        </DropdownMenuContent>
                      </DropdownMenu>
                    )}

                    {!isEmbedded && !hideTerminal && (
                      <Button
                        variant="ghost"
                        className="h-8 px-2 gap-1 text-[11px] text-muted-foreground hover:text-foreground shrink-0 cursor-pointer"
                        title={t("chat.interface.enterTerminal")}
                        onClick={() => {
                          setChatMode("chat")
                          setTerminalMode(true)
                        }}
                      >
                        <Terminal size={14} />
                        <span className="hidden lg:inline">
                          {t("chat.interface.terminalLabel", {
                            defaultValue: "终端",
                          })}
                        </span>
                      </Button>
                    )}

                    {!hideVoice && (
                      <DropdownMenu>
                        <DropdownMenuTrigger asChild>
                          <Button
                            variant={voiceMode !== "off" ? "secondary" : "ghost"}
                            size="icon"
                            disabled={isSending}
                            className={cn(
                              "h-8 w-8",
                              voiceMode === "dictation" && "text-info bg-info/10",
                              voiceMode === "dialogue" &&
                                "text-success bg-success/10",
                              voiceState !== "idle" && "animate-pulse",
                            )}
                          >
                            <Mic className="h-4 w-4" />
                          </Button>
                        </DropdownMenuTrigger>
                        <DropdownMenuContent align="start" className="min-w-[40px]">
                          <TooltipProvider delayDuration={100}>
                            <Tooltip>
                              <TooltipTrigger asChild>
                                <DropdownMenuItem
                                  onClick={() => setVoiceMode("dictation")}
                                  className={
                                    voiceMode === "dictation" ? "text-info" : ""
                                  }
                                >
                                  <FileText className="h-4 w-4" />
                                </DropdownMenuItem>
                              </TooltipTrigger>
                              <TooltipContent side="left">
                                {t("chat.voice.dictationMode")}
                              </TooltipContent>
                            </Tooltip>
                          </TooltipProvider>
                        </DropdownMenuContent>
                      </DropdownMenu>
                    )}
                  </>
                )}
              </div>

              {/* 右组：模型选择 + 发送/停止 */}
              <div className="ml-auto flex items-center gap-1.5 shrink-0">
                {!isTerminalMode && (
                  <>
                    {!hideAutoSpeak && (
                      <TooltipProvider delayDuration={100}>
                        <Tooltip>
                          <TooltipTrigger asChild>
                            <Button
                              variant={autoSpeak ? "secondary" : "ghost"}
                              size="icon"
                              onClick={toggleAutoSpeak}
                              className="h-8 w-8 hidden xl:inline-flex"
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
                    )}
                    <ModelSelectorWrapper isSending={isSending} />
                  </>
                )}
                <Button
                  onClick={() => (isAgentWorking ? onStop() : handleSend())}
                  disabled={
                    (!inputValue.trim() &&
                      pickedFiles.length === 0 &&
                      !isAgentWorking) ||
                    isSending ||
                    isUploading
                  }
                  size="icon"
                  className={cn(
                    "h-9 w-9 rounded-full transition-all shrink-0",
                    isAgentWorking || isStopPending
                      ? "bg-destructive hover:bg-destructive/90 text-white"
                      : "bg-primary hover:bg-primary/90 text-primary-foreground shadow-sm disabled:opacity-40 disabled:shadow-none",
                  )}
                  title={isAgentWorking ? t("common.stop") : t("common.send")}
                >
                  {isStopPending ? (
                    <Loader2 size={16} className="animate-spin" />
                  ) : isAgentWorking ? (
                    <Square size={15} fill="currentColor" />
                  ) : (
                    <ArrowUp size={17} strokeWidth={2.5} />
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
