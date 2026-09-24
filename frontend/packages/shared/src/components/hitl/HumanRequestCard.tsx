import {useState} from "react"
import {useTranslation} from "react-i18next"
import {Ban, CheckCircle2, FileCheck2, FolderGit2, Loader2, Play, XCircle,} from "lucide-react"

import {Button} from "../ui/button"
import {Checkbox} from "../ui/checkbox"
import {Label} from "../ui/label"
import {RadioGroup, RadioGroupItem} from "../ui/radio-group"
import {Textarea} from "../ui/textarea"
import type {HumanRequestCardProps} from "./types"

/**
 * EvoLoop 通用人在回路协同治理卡片 (Universal HumanRequestCard)
 * 纯受控组件，可在 Chat 对话流、自主值守工作台（Duty Workbench）、审批中心等多端零成本复用：
 * - 7 种标准交互模式：text / choice / multi_choice / approval / confirmation / project_switch / file_select
 * - 解耦单例 Store，完全由 props (request, onRespond, onCancel, onReject) 驱动
 * - 支持插槽注入富文本渲染 (renderContent) 与项目切换器 (renderProjectSwitcher)
 */
export function HumanRequestCard({
  request,
  onRespond,
  onCancel,
  onReject,
  renderProjectSwitcher,
  renderContent,
  className = "",
}: HumanRequestCardProps) {
  const { t } = useTranslation()
  const [input, setInput] = useState("")
  const [customValue, setCustomValue] = useState("")
  const [selected, setSelected] = useState<string[]>([])
  const [customEnabled, setCustomEnabled] = useState(false)
  const [isSubmitting, setIsSubmitting] = useState(false)
  const [selectedProject, setSelectedProject] = useState<{
    id: number | string
    name: string
    path?: string
  } | null>(null)

  const isResolved =
    request.status === "completed" ||
    request.status === "cancelled" ||
    request.status === "rejected"

  const handleResponse = async (
    response: string,
    grantMode?: "once" | "always" | "dir" | "default",
  ) => {
    if (!onRespond) return
    setIsSubmitting(true)
    try {
      await onRespond(response, grantMode)
    } finally {
      setIsSubmitting(false)
    }
  }

  const handleCancelAction = async () => {
    if (!onCancel) return
    setIsSubmitting(true)
    try {
      await onCancel()
    } finally {
      setIsSubmitting(false)
    }
  }

  const handleRejectAction = async () => {
    if (onReject) {
      setIsSubmitting(true)
      try {
        await onReject()
      } finally {
        setIsSubmitting(false)
      }
    } else {
      await handleResponse(t("common.reject", "拒绝"))
    }
  }

  const handleProjectSelect = async (project: {
    id: number | string
    name: string
    path?: string
  }) => {
    setSelectedProject(project)
    setIsSubmitting(true)
    try {
      const isTemporary = request.payload?.temporary === true
      if (isTemporary) {
        const tempContext = {
          type: "temp_project",
          project_id: project.id,
          project_name: project.name,
        }
        await onRespond?.(JSON.stringify(tempContext))
      } else {
        await onRespond?.(String(project.id))
      }
    } finally {
      setIsSubmitting(false)
    }
  }

  const renderTextOrContent = (text?: string | null) => {
    if (!text) return null
    if (renderContent) return renderContent(text)
    return <div className="whitespace-pre-wrap">{text}</div>
  }

  return (
    <div className={`w-full my-2 animate-in fade-in slide-in-from-top-2 duration-300 ${className}`}>
      <div className="space-y-2">
        {/* ── 1. 引导 Prompt ── */}
        <div className="text-[14px] font-medium leading-relaxed border-l-2 border-primary/60 pl-3 py-0.5 text-foreground">
          {renderTextOrContent(request.prompt)}
        </div>

        {/* ── 2. 结构化上下文 Context ── */}
        {request.context && (
          <div className="bg-muted/40 p-2.5 px-3 rounded-md border border-border/40 text-xs font-mono leading-relaxed text-muted-foreground">
            {renderTextOrContent(request.context)}
          </div>
        )}

        {/* ── 3. 交互表单区 ── */}
        <div className="bg-background border border-border/60 rounded-lg p-2.5 shadow-2xs">
          {!isResolved && (
            <div className="mb-2">
              {/* 模式 A: 单行 / 多行自由文本 */}
              {request.type === "text" && (
                <Textarea
                  value={input}
                  onChange={(e) => setInput(e.target.value)}
                  placeholder={t("chat.request.placeholder", "请输入您的回复或指示…")}
                  className="min-h-[80px] bg-muted/20 border-input/60 focus-visible:ring-1 focus-visible:ring-primary/40 resize-none text-xs"
                />
              )}

              {/* 模式 B: 单选题 (Choice) */}
              {request.type === "choice" && request.options && (
                <div className="space-y-1.5">
                  <RadioGroup
                    value={input}
                    onValueChange={setInput}
                    className="gap-1.5"
                  >
                    {request.options.map((opt, i) => (
                      <div
                        key={i}
                        className={`flex items-center space-x-2.5 p-2 px-2.5 rounded-md border transition-all cursor-pointer ${
                          input === opt
                            ? "border-primary/50 bg-primary/10 text-foreground font-medium"
                            : "border-border/50 hover:border-primary/20 hover:bg-muted/40 text-muted-foreground"
                        }`}
                        onClick={() => setInput(opt)}
                      >
                        <RadioGroupItem
                          value={opt}
                          id={`opt-${request.id}-${i}`}
                          className="border-primary/40 shrink-0"
                        />
                        <Label
                          htmlFor={`opt-${request.id}-${i}`}
                          className="text-xs cursor-pointer flex-1 leading-relaxed break-words"
                        >
                          {opt}
                        </Label>
                      </div>
                    ))}

                    {/* 标配补充自定义输入单选项 */}
                    <div
                      className={`flex items-center space-x-2.5 p-2 px-2.5 rounded-md border transition-all cursor-pointer ${
                        input === "__custom__"
                          ? "border-primary/50 bg-primary/10 text-foreground font-medium"
                          : "border-border/50 hover:border-primary/20 hover:bg-muted/40 text-muted-foreground"
                      }`}
                      onClick={() => setInput("__custom__")}
                    >
                      <RadioGroupItem
                        value="__custom__"
                        id={`opt-${request.id}-custom`}
                        className="border-primary/40 shrink-0"
                      />
                      <Label
                        htmlFor={`opt-${request.id}-custom`}
                        className="text-xs cursor-pointer flex-1 leading-relaxed break-words"
                      >
                        {t("common.customInput", "自定义输入…")}
                      </Label>
                    </div>
                  </RadioGroup>

                  {/* 选中自定义输入时展开文本框 */}
                  {input === "__custom__" && (
                    <Textarea
                      value={customValue}
                      onChange={(e) => setCustomValue(e.target.value)}
                      placeholder={t("common.customInputPlaceholder", "请输入您的具体要求或指示…")}
                      className="min-h-[60px] mt-1.5 bg-muted/20 border-input/60 focus-visible:ring-1 focus-visible:ring-primary/40 resize-none text-xs"
                      autoFocus
                    />
                  )}
                </div>
              )}

              {/* 模式 C: 多选题 (Multi Choice) */}
              {request.type === "multi_choice" && request.options && (
                <div className="space-y-1.5">
                  {request.options.map((opt, i) => {
                    const isChecked = selected.includes(opt)
                    return (
                      <div
                        key={i}
                        className={`flex items-center space-x-2.5 p-2 px-2.5 rounded-md border transition-all cursor-pointer ${
                          isChecked
                            ? "border-primary/50 bg-primary/10 text-foreground font-medium"
                            : "border-border/50 hover:border-primary/20 hover:bg-muted/40 text-muted-foreground"
                        }`}
                        onClick={() => {
                          setSelected((s) =>
                            isChecked ? s.filter((x) => x !== opt) : [...s, opt]
                          )
                        }}
                      >
                        <Checkbox
                          id={`mopt-${request.id}-${i}`}
                          checked={isChecked}
                          onCheckedChange={(c) => {
                            if (c) setSelected((s) => [...s, opt])
                            else setSelected((s) => s.filter((x) => x !== opt))
                          }}
                          className="border-primary/40 shrink-0"
                        />
                        <Label
                          htmlFor={`mopt-${request.id}-${i}`}
                          className="text-xs cursor-pointer flex-1 leading-relaxed break-words"
                        >
                          {opt}
                        </Label>
                      </div>
                    )
                  })}

                  {/* 自定义多选补充输入 */}
                  <div
                    className={`flex items-center space-x-2.5 p-2 px-2.5 rounded-md border transition-all cursor-pointer ${
                      customEnabled
                        ? "border-primary/50 bg-primary/10 text-foreground font-medium"
                        : "border-border/50 hover:border-primary/20 hover:bg-muted/40 text-muted-foreground"
                    }`}
                    onClick={() => setCustomEnabled(!customEnabled)}
                  >
                    <Checkbox
                      id={`mopt-${request.id}-custom`}
                      checked={customEnabled}
                      onCheckedChange={(c) => setCustomEnabled(c === true)}
                      className="border-primary/40 shrink-0"
                    />
                    <Label
                      htmlFor={`mopt-${request.id}-custom`}
                      className="text-xs cursor-pointer flex-1 leading-relaxed break-words"
                    >
                      {t("common.customInput", "自定义输入…")}
                    </Label>
                  </div>

                  {customEnabled && (
                    <Textarea
                      value={customValue}
                      onChange={(e) => setCustomValue(e.target.value)}
                      placeholder={t("common.customInputPlaceholder", "请输入补充指令（多项请用逗号隔开）…")}
                      className="min-h-[60px] mt-1.5 bg-muted/20 border-input/60 focus-visible:ring-1 focus-visible:ring-primary/40 resize-none text-xs"
                      autoFocus
                    />
                  )}
                </div>
              )}

              {/* 模式 D: 项目切换选择 (Project Switch) */}
              {request.type === "project_switch" && (
                <div className="space-y-3">
                  {!selectedProject ? (
                    renderProjectSwitcher ? (
                      renderProjectSwitcher({
                        onSelect: handleProjectSelect,
                        disabled: isSubmitting,
                      })
                    ) : (
                      <div className="text-xs text-muted-foreground p-3 border rounded border-dashed text-center">
                        {t("chat.interrupted.selectProject", "请选择目标项目")}
                      </div>
                    )
                  ) : (
                    <div className="p-3 rounded-lg border bg-primary/5 border-primary/20 flex items-center gap-3">
                      <FolderGit2 className="h-4 w-4 text-primary shrink-0" />
                      <div className="flex-1 min-w-0 text-xs">
                        <p className="font-semibold text-foreground truncate">{selectedProject.name}</p>
                        {selectedProject.path && (
                          <p className="text-[10px] text-muted-foreground truncate font-mono">{selectedProject.path}</p>
                        )}
                      </div>
                    </div>
                  )}
                </div>
              )}

              {/* 模式 E: 文件选择 (File Select) */}
              {request.type === "file_select" && (
                <div className="space-y-3">
                  <Button
                    variant="outline"
                    onClick={() => {
                      const fileInput = document.createElement("input")
                      fileInput.type = "file"
                      fileInput.multiple = request.payload?.multiple || false
                      if (request.payload?.file_types) {
                        fileInput.accept = request.payload.file_types.join(",")
                      }
                      fileInput.onchange = (e) => {
                        const files = (e.target as HTMLInputElement).files
                        if (files && files.length > 0) {
                          const paths = Array.from(files)
                            .map((f) => (f as unknown as { path?: string }).path || f.name)
                            .join(", ")
                          setInput(paths)
                        }
                      }
                      fileInput.click()
                    }}
                    className="w-full h-10 justify-start gap-2.5 border-dashed border-2 hover:border-primary/40 hover:bg-primary/5 text-xs"
                    disabled={isSubmitting}
                  >
                    <FolderGit2 className="h-4 w-4 text-primary/70 shrink-0" />
                    <span className="truncate">
                      {input || t("chat.request.selectFiles", "点击选择本地文件…")}
                    </span>
                  </Button>
                </div>
              )}
            </div>
          )}

          {/* ── 4. 底部操作栏 ── */}
          <div className="flex justify-end items-center gap-2 border-t border-border/30 pt-2">
            {!isResolved ? (
              <>
                {onCancel && (
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={handleCancelAction}
                    disabled={isSubmitting}
                    className="h-7 text-muted-foreground hover:text-destructive hover:bg-destructive/10 text-xs px-2.5"
                  >
                    <Ban className="mr-1 h-3 w-3" />
                    {t("common.cancel", "取消")}
                  </Button>
                )}

                <div className="flex items-center gap-1.5">
                  {/* 普通单选 / 多选 / 文本 / 文件提交 */}
                  {(request.type === "text" ||
                    request.type === "choice" ||
                    request.type === "multi_choice" ||
                    request.type === "file_select") && (
                    <Button
                      size="sm"
                      onClick={() => {
                        const finalVal =
                          request.type === "choice" && input === "__custom__"
                            ? customValue.trim()
                            : request.type === "multi_choice"
                            ? [
                                ...selected,
                                ...(customEnabled && customValue.trim()
                                  ? customValue.split(/[,，\s]+/).filter(Boolean)
                                  : []),
                              ].join(",")
                            : input.trim()

                        if (finalVal) void handleResponse(finalVal)
                      }}
                      disabled={
                        isSubmitting ||
                        (request.type === "choice" && input === "__custom__"
                          ? !customValue.trim()
                          : request.type === "multi_choice"
                          ? selected.length === 0 && !(customEnabled && customValue.trim())
                          : !input.trim())
                      }
                      className="h-7 px-3.5 text-xs font-semibold gap-1"
                    >
                      {isSubmitting ? (
                        <Loader2 className="h-3 w-3 animate-spin" />
                      ) : (
                        <Play className="h-3 w-3 fill-current" />
                      )}
                      <span>{t("common.submit", "确定提交")}</span>
                    </Button>
                  )}

                  {/* 高危授权 (Approval) 四级治理动作 */}
                  {request.type === "approval" && (
                    <>
                      <Button
                        variant="outline"
                        size="sm"
                        onClick={handleRejectAction}
                        disabled={isSubmitting}
                        className="h-7 px-3 border-destructive/30 text-destructive hover:bg-destructive/10 text-xs font-medium"
                      >
                        <XCircle className="mr-1 h-3 w-3" />
                        {t("common.reject", "拒绝")}
                      </Button>
                      <Button
                        variant="outline"
                        size="sm"
                        onClick={() => handleResponse(t("common.approve", "允许"), "once")}
                        disabled={isSubmitting}
                        className="h-7 px-3 text-xs font-medium"
                      >
                        <CheckCircle2 className="mr-1 h-3 w-3 text-primary" />
                        {t("hitl.approveOnce", "仅本次允许")}
                      </Button>
                      {/* 授权父目录（仅授权门控请求显示）：prefix 递归放行该目录树 */}
                      {request.payload?.resource_path && (
                        <Button
                          variant="outline"
                          size="sm"
                          onClick={() => handleResponse(t("common.approve", "允许"), "dir")}
                          disabled={isSubmitting}
                          className="h-7 px-3 text-xs font-medium"
                        >
                          <FolderGit2 className="mr-1 h-3 w-3 text-primary/80" />
                          {t("hitl.approveParentDir", "授权父目录")}
                        </Button>
                      )}
                      <Button
                        size="sm"
                        onClick={() => handleResponse(t("common.approve", "允许"), "always")}
                        disabled={isSubmitting}
                        className="h-7 px-3 text-xs font-semibold"
                      >
                        <CheckCircle2 className="mr-1 h-3 w-3" />
                        {t("hitl.approveAlways", "总是允许")}
                      </Button>
                    </>
                  )}

                  {/* 二元确认 (Confirmation) */}
                  {request.type === "confirmation" && (
                    <>
                      <Button
                        variant="outline"
                        size="sm"
                        onClick={() => handleResponse(t("common.no", "否"))}
                        disabled={isSubmitting}
                        className="h-7 px-3 border-destructive/30 text-destructive hover:bg-destructive/10 text-xs font-medium"
                      >
                        <XCircle className="mr-1 h-3 w-3" />
                        {t("common.no", "否")}
                      </Button>
                      <Button
                        size="sm"
                        onClick={() => handleResponse(t("common.yes", "是"))}
                        disabled={isSubmitting}
                        className="h-7 px-3 text-xs font-semibold"
                      >
                        <CheckCircle2 className="mr-1 h-3 w-3" />
                        {t("common.yes", "是")}
                      </Button>
                    </>
                  )}
                </div>
              </>
            ) : (
              /* 事后审计封存态印章 */
              <div
                className={`flex items-center gap-1.5 px-3 py-1 rounded-full text-[11px] font-semibold ${
                  request.status === "completed"
                    ? "bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 border border-emerald-500/20"
                    : "bg-destructive/10 text-destructive border border-destructive/20"
                }`}
              >
                {request.status === "completed" ? (
                  <>
                    <FileCheck2 className="h-3.5 w-3.5" />
                    <span>{t("chat.request.completed", "已授权 / 已采纳")}</span>
                  </>
                ) : (
                  <>
                    <XCircle className="h-3.5 w-3.5" />
                    <span>{t("chat.request.cancelled", "已取消 / 已拒绝")}</span>
                  </>
                )}
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  )
}
