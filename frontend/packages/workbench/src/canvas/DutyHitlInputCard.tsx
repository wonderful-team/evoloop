import { useState } from "react"
import { Button } from "@evoloop/shared/components/ui/button"
import { AgentService } from "@/client/sdk.gen"
import { useQueryClient } from "@tanstack/react-query"
import { Ban, CheckCircle2, CornerDownLeft, Loader2, Sparkles, X } from "lucide-react"

export interface DutyHitlItem {
  request_id: string
  thread_id: string
  type: string
  description: string
  context?: string | null
  options?: string[]
  task_id?: string | null
  task_title?: string | null
  task_no?: number | null
}

interface DutyHitlInputCardProps {
  hitl: DutyHitlItem
  onClose?: () => void
  onResolved?: () => Promise<void> | void
}

export function DutyHitlInputCard({
  hitl,
  onClose,
  onResolved,
}: DutyHitlInputCardProps) {
  const qc = useQueryClient()
  const [selectedOption, setSelectedOption] = useState<string | null>(
    hitl.options && hitl.options.length > 0 ? hitl.options[0] : null
  )
  const [customEnabled, setCustomEnabled] = useState(false)
  const [customInput, setCustomInput] = useState("")
  const [isSubmitting, setIsSubmitting] = useState(false)

  const handleSubmit = async (responseValue?: string) => {
    const val =
      responseValue ??
      (customEnabled ? customInput.trim() : selectedOption ?? "approve")
    if (!val) return

    setIsSubmitting(true)
    try {
      await AgentService.resumeChat({
        requestBody: {
          thread_id: hitl.thread_id,
          user_input: val,
          grant_mode: "once",
        },
      })
      await onResolved?.()
      void qc.invalidateQueries({ queryKey: ["dutyHitl"] })
      void qc.invalidateQueries({ queryKey: ["dutyQueue"] })
    } finally {
      setIsSubmitting(false)
    }
  }

  const handleReject = async () => {
    setIsSubmitting(true)
    try {
      await AgentService.stopChat({
        requestBody: { thread_id: hitl.thread_id, message: "" },
      })
      await AgentService.cancelHitlRequest({
        requestBody: {
          thread_id: hitl.thread_id,
          reason: "值守操作员驳回",
        },
      })
      await onResolved?.()
      void qc.invalidateQueries({ queryKey: ["dutyHitl"] })
      void qc.invalidateQueries({ queryKey: ["dutyQueue"] })
    } finally {
      setIsSubmitting(false)
    }
  }

  const hasOptions = hitl.options && hitl.options.length > 0

  return (
    <div className="w-full p-4 space-y-3 animate-in fade-in duration-200">
      {/* ── 顶部 Header ── */}
      <div className="flex items-center justify-between gap-2">
        <div className="flex items-center gap-2 min-w-0">
          <span className="relative flex h-2 w-2 shrink-0">
            <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-amber-400 opacity-75" />
            <span className="relative inline-flex rounded-full h-2 w-2 bg-amber-500" />
          </span>
          <span className="text-xs font-semibold text-foreground tracking-tight">
            待决策审批
          </span>
          {hitl.task_title && (
            <span className="text-[11px] font-mono text-muted-foreground bg-muted/60 px-2 py-0.5 rounded-md border border-border/40 truncate max-w-[280px]">
              {hitl.task_no ? `#T-${hitl.task_no} ` : ""}
              {hitl.task_title}
            </span>
          )}
        </div>

        {onClose && (
          <button
            type="button"
            onClick={onClose}
            title="取消聚焦，返回全局对话输入"
            className="h-6 w-6 rounded-md hover:bg-muted/80 text-muted-foreground hover:text-foreground flex items-center justify-center transition-colors cursor-pointer"
          >
            <X className="h-3.5 w-3.5" />
          </button>
        )}
      </div>

      {/* ── 核心问题描述 ── */}
      <div className="border-l-2 border-amber-500/70 pl-2.5 py-0.5 space-y-1.5">
        <div className="text-xs font-medium text-foreground leading-relaxed break-words">
          {hitl.description || hitl.context || "Agent 需要您对此步骤进行确认或做出决策"}
        </div>

        {hitl.context && hitl.context !== hitl.description && (
          <div className="bg-muted/40 p-2 rounded-md border border-border/30 text-[11px] font-mono text-muted-foreground break-words max-h-20 overflow-y-auto">
            {hitl.context}
          </div>
        )}
      </div>

      {/* ── 选项决策区（垂直卡片条目排版） ── */}
      {hasOptions && (
        <div className="space-y-1.5 max-h-56 overflow-y-auto pr-0.5">
          {hitl.options!.map((opt, idx) => {
            const isSelected = !customEnabled && selectedOption === opt
            return (
              <div
                key={idx}
                onClick={() => {
                  setCustomEnabled(false)
                  setSelectedOption(opt)
                }}
                onDoubleClick={() => handleSubmit(opt)}
                className={`group flex items-start gap-2.5 p-2.5 rounded-lg border text-xs cursor-pointer transition-all ${
                  isSelected
                    ? "border-primary/60 bg-primary/8 text-foreground font-medium shadow-xs"
                    : "border-border/50 hover:border-border hover:bg-muted/40 text-muted-foreground hover:text-foreground"
                }`}
              >
                {/* 单选 Radio 状态 */}
                <div className="pt-0.5 shrink-0">
                  <span
                    className={`flex h-3.5 w-3.5 rounded-full border items-center justify-center transition-colors ${
                      isSelected
                        ? "border-primary bg-primary text-primary-foreground"
                        : "border-muted-foreground/40 group-hover:border-muted-foreground"
                    }`}
                  >
                    {isSelected && (
                      <span className="h-1.5 w-1.5 rounded-full bg-white dark:bg-black" />
                    )}
                  </span>
                </div>

                {/* 选项文本 */}
                <span className="flex-1 leading-relaxed break-words">{opt}</span>

                {/* 双击提示 */}
                {isSelected && (
                  <span className="text-[10px] text-primary/70 shrink-0 self-center hidden sm:inline-flex items-center gap-0.5 font-mono">
                    <CornerDownLeft className="h-2.5 w-2.5" /> 双击执行
                  </span>
                )}
              </div>
            )
          })}

          {/* 补充自定义输入选项 */}
          <div
            onClick={() => setCustomEnabled(true)}
            className={`flex items-start gap-2.5 p-2.5 rounded-lg border text-xs cursor-pointer transition-all ${
              customEnabled
                ? "border-primary/60 bg-primary/8 text-foreground font-medium shadow-xs"
                : "border-border/50 hover:border-border hover:bg-muted/40 text-muted-foreground hover:text-foreground"
            }`}
          >
            <div className="pt-0.5 shrink-0">
              <span
                className={`flex h-3.5 w-3.5 rounded-full border items-center justify-center transition-colors ${
                  customEnabled
                    ? "border-primary bg-primary text-primary-foreground"
                    : "border-muted-foreground/40"
                }`}
              >
                {customEnabled && (
                  <span className="h-1.5 w-1.5 rounded-full bg-white dark:bg-black" />
                )}
              </span>
            </div>
            <span className="flex-1">自定义指示回复…</span>
          </div>

          {customEnabled && (
            <div className="pt-1">
              <input
                type="text"
                autoFocus
                value={customInput}
                onChange={(e) => setCustomInput(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === "Enter" && !e.shiftKey) {
                    e.preventDefault()
                    void handleSubmit()
                  }
                }}
                placeholder="请输入您的具体决策或指令（按回车执行）…"
                className="w-full h-8 px-3 rounded-md bg-muted/30 border border-input/60 focus:border-primary focus:ring-1 focus:ring-primary text-xs text-foreground outline-none transition-all"
              />
            </div>
          )}
        </div>
      )}

      {/* ── 底部操作栏 ── */}
      <div className="flex items-center justify-between gap-2 pt-2 border-t border-border/40">
        <div className="text-[11px] text-muted-foreground flex items-center gap-1">
          <Sparkles className="h-3 w-3 text-amber-500/70 shrink-0" />
          <span>决策后 Agent 将在现场立即恢复推进</span>
        </div>

        <div className="flex items-center gap-2">
          <Button
            size="sm"
            variant="ghost"
            disabled={isSubmitting}
            className="h-7 text-xs text-muted-foreground hover:text-destructive hover:bg-destructive/10"
            onClick={handleReject}
          >
            <Ban className="h-3 w-3 mr-1" />
            驳回终止
          </Button>

          <Button
            size="sm"
            disabled={isSubmitting || (customEnabled && !customInput.trim())}
            className="h-7 px-3 text-xs bg-primary text-primary-foreground hover:bg-primary/90 font-medium"
            onClick={() => handleSubmit()}
          >
            {isSubmitting ? (
              <Loader2 className="h-3 w-3 animate-spin mr-1" />
            ) : (
              <CheckCircle2 className="h-3 w-3 mr-1" />
            )}
            {hasOptions
              ? customEnabled
                ? "发送自定义指示"
                : "执行所选策略"
              : "授权继续"}
          </Button>
        </div>
      </div>
    </div>
  )
}
