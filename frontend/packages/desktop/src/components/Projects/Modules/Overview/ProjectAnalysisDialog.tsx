// 项目分析弹窗 — 包含指令(Macro)生成入口
// 概念说明：前端显示"指令"，后端概念为 Macro/appmap

import {Button} from "@evoloop/shared/components/ui/button"
import {Checkbox} from "@evoloop/shared/components/ui/checkbox"
import {
    Dialog,
    DialogContent,
    DialogDescription,
    DialogFooter,
    DialogHeader,
    DialogTitle,
} from "@evoloop/shared/components/ui/dialog"
import {AlertCircle, CheckCircle2, Clock, FileText, Loader2, Search, Shield, Zap,} from "lucide-react"
import {useEffect, useRef, useState} from "react"
import {useTranslation} from "react-i18next"
import {toast} from "sonner"
import {ProjectsService} from "@/client"
import {ProjectProfilesService} from "@/client/sdk.gen"
import {useSystemEvent} from "@/hooks/useSystemEvent"

interface ProjectAnalysisDialogProps {
  projectId: number
  open: boolean
  onOpenChange: (open: boolean) => void
  onDiscovered?: () => void
}

interface ArtifactItem {
  key: string
  label: string
  desc: string
  icon: any
  checked: boolean
  status: string
}

interface ProgressStep {
  key: string
  label: string
  status: "pending" | "running" | "completed" | "failed"
}

export function ProjectAnalysisDialog({
  projectId,
  open,
  onOpenChange,
  onDiscovered,
}: ProjectAnalysisDialogProps) {
  const { t } = useTranslation()
  const [loading, setLoading] = useState(true)
  const [generating, setGenerating] = useState(false)
  const [recordSecrets, setRecordSecrets] = useState(false)
  const [items, setItems] = useState<ArtifactItem[]>([])

  // Progress state
  const [isAnalyzing, setIsAnalyzing] = useState(false)
  const [steps, setSteps] = useState<ProgressStep[]>([])

  // Refs to handle sequential execution of generation tasks after indexing finishes
  const pendingDispatchItemsRef = useRef<string[]>([])
  const shouldDiscoverProfileRef = useRef(false)

  const fetchStatus = async () => {
    if (!projectId || !open) return
    setLoading(true)
    try {
      const [statusRes, profileRes] = await Promise.all([
        ProjectsService.listGenerationStatusEndpoint({ projectId }).catch(
          () => ({ items: [] }),
        ),
        ProjectProfilesService.projectsGetProfile({ projectId }),
      ])
      const map: Record<string, string> = {}
      for (const item of (statusRes as any).items || []) {
        map[item.item] = item.status
      }
      map.overview = profileRes.exists ? "completed" : "pending"

      const allItems: ArtifactItem[] = [
        {
          key: "overview",
          label: t("generation.dialog.items.overview"),
          desc: t("generation.dialog.items.overviewDesc"),
          icon: FileText,
          checked: false,
          status: map.overview || "pending",
        },
        {
          key: "wiki",
          label: t("generation.dialog.items.wiki"),
          desc: t("generation.dialog.items.wikiDesc"),
          icon: FileText,
          checked: false,
          status: map.wiki || "pending",
        },
        {
          key: "appmap",
          label: t("generation.dialog.items.appmap"),
          desc: t("generation.dialog.items.appmapDesc"),
          icon: Zap,
          checked: false,
          status: map.appmap || "pending",
        },
      ]

      const hasPending = allItems.some((i) => i.status === "pending")
      if (hasPending) {
        allItems.forEach((i) => {
          i.checked = i.status !== "completed"
        })
      }

      setItems(allItems)
    } catch {
      // ignore
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    if (open) {
      setRecordSecrets(false)
      setGenerating(false)
      setIsAnalyzing(false)
      setSteps([])
      fetchStatus()
    }
  }, [projectId, open])

  const triggerPendingGenerations = async () => {
    if (pendingDispatchItemsRef.current.length === 0 && !shouldDiscoverProfileRef.current) return

    const itemsToDispatch = [...pendingDispatchItemsRef.current]
    const discoverProfile = shouldDiscoverProfileRef.current

    // Clear refs
    pendingDispatchItemsRef.current = []
    shouldDiscoverProfileRef.current = false

    try {
      const promises: Promise<any>[] = []
      if (itemsToDispatch.length > 0) {
        promises.push(
          ProjectsService.dispatchGenerationEndpoint({
            projectId,
            requestBody: { project_id: projectId, items: itemsToDispatch },
          }),
        )
      }
      if (discoverProfile) {
        promises.push(
          ProjectProfilesService.projectsDiscoverProfile({
            projectId,
            requestBody: {
              project_id: projectId,
              record_secrets: recordSecrets,
            },
          }),
        )
      }
      await Promise.all(promises)
      toast.info("静态分析已就绪，已提交后续生成任务，正在读取分析进度...")
    } catch {
      toast.error("提交后续生成任务失败，请手动重试")
      setGenerating(false)
    }
  }

  // Listen to indexing status changes
  useSystemEvent("indexing.status", (event) => {
    if (!isAnalyzing || event.data?.project_id !== projectId) return
    const status = event.data?.status
    setSteps((prev) =>
      prev.map((step) => {
        if (step.key === "indexing") {
          if (status === "indexing" || status === "queued")
            return { ...step, status: "running" }
          if (status === "done") {
            triggerPendingGenerations()
            return { ...step, status: "completed" }
          }
          if (status === "error" || status === "failed") {
            setGenerating(false)
            toast.error("项目静态结构分析失败，停止生成后续产物")
            return { ...step, status: "failed" }
          }
        }
        return step
      }),
    )
  })

  // Listen to generation status changes
  useSystemEvent("generation.status", (event) => {
    if (!isAnalyzing || event.data?.project_id !== projectId) return
    const { item, status } = event.data
    setSteps((prev) =>
      prev.map((step) => {
        if (step.key === item) {
          if (status === "running") return { ...step, status: "running" }
          if (status === "completed") return { ...step, status: "completed" }
          if (status === "failed") return { ...step, status: "failed" }
        }
        return step
      }),
    )
  })

  // Watch steps to finish analyzing when all reach terminal states
  useEffect(() => {
    if (!isAnalyzing || steps.length === 0) return
    const allTerminal = steps.every(
      (s) => s.status === "completed" || s.status === "failed",
    )
    if (allTerminal) {
      setGenerating(false)
      const hasFailed = steps.some((s) => s.status === "failed")
      if (hasFailed) {
        toast.error("部分项目产物分析生成失败，请检查详情日志")
      } else {
        toast.success("项目生成与分析流水线已圆满完成！")
      }
      onDiscovered?.()
    }
  }, [steps, isAnalyzing])

  const handleToggle = (key: string) => {
    if (isAnalyzing) return
    setItems((prev) =>
      prev.map((i) => (i.key === key ? { ...i, checked: !i.checked } : i)),
    )
  }

  const handleGenerate = async () => {
    const selected = items.filter((i) => i.checked)
    if (selected.length === 0) {
      toast.error(t("generation.dialog.selectAtLeastOne"))
      return
    }

    // Initialize progress steps
    const initialSteps: ProgressStep[] = [
      {
        key: "indexing",
        label: "项目底层静态结构分析与脏检查",
        status: "running",
      },
    ]
    if (selected.some((i) => i.key === "overview")) {
      initialSteps.push({
        key: "summary",
        label: "AI 项目画像说明书构建",
        status: "pending",
      })
    }
    if (selected.some((i) => i.key === "wiki")) {
      initialSteps.push({
        key: "wiki",
        label: "AI 业务功能大纲 Wiki 文档编译",
        status: "pending",
      })
    }
    if (selected.some((i) => i.key === "appmap")) {
      initialSteps.push({
        key: "appmap",
        label: "API 路由与数据库网络拓扑提取",
        status: "pending",
      })
    }

    setSteps(initialSteps)
    setIsAnalyzing(true)
    setGenerating(true)

    const dispatchItems = selected
      .map((i) => (i.key === "overview" ? "summary" : i.key))
      .filter((k): k is string => !!k)

    pendingDispatchItemsRef.current = dispatchItems
    shouldDiscoverProfileRef.current = selected.some((i) => i.key === "overview")

    try {
      // 1. Trigger codebase indexing first
      await ProjectsService.runIndexingEndpoint({
        requestBody: { project_id: projectId },
      })
      toast.info("已启动项目底层静态结构分析与脏检查...")
    } catch {
      toast.error(t("generation.dialog.submitFailed"))
      setIsAnalyzing(false)
      setGenerating(false)
    }
  }

  const statusLabel = (status: string) => {
    if (status === "completed") return t("generation.status.completed")
    if (status === "running") return t("generation.status.running")
    if (status === "failed") return t("generation.status.failed")
    return t("generation.status.pending")
  }

  const allFinished =
    steps.length > 0 &&
    steps.every((s) => s.status === "completed" || s.status === "failed")

  return (
    <Dialog
      open={open}
      onOpenChange={isAnalyzing && !allFinished ? () => {} : onOpenChange}
    >
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <Search className="h-5 w-5 text-primary" />
            {isAnalyzing
              ? "正在进行项目分析与初始化"
              : t("generation.dialog.title")}
          </DialogTitle>
          <DialogDescription>
            {isAnalyzing
              ? "系统正在通过底层 AST 分析代码符号并调度 AI 代理自动解析业务模块，请耐心等待以下阶段完成。"
              : t("generation.dialog.description")}
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-3 py-2">
          {loading ? (
            <div className="flex justify-center py-8">
              <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />
            </div>
          ) : isAnalyzing ? (
            // Live Progress Flow UI
            <div className="space-y-3 bg-muted/20 p-4 rounded-lg border border-border/80">
              {steps.map((step) => (
                <div
                  key={step.key}
                  className="flex items-center justify-between text-xs py-1"
                >
                  <div className="flex items-center gap-2.5">
                    {step.status === "running" ? (
                      <Loader2 className="h-4 w-4 animate-spin text-blue-500 shrink-0" />
                    ) : step.status === "completed" ? (
                      <CheckCircle2 className="h-4 w-4 text-emerald-500 shrink-0" />
                    ) : step.status === "failed" ? (
                      <AlertCircle className="h-4 w-4 text-red-500 shrink-0" />
                    ) : (
                      <Clock className="h-4 w-4 text-muted-foreground shrink-0" />
                    )}
                    <span
                      className={`font-medium ${step.status === "completed" ? "text-foreground" : step.status === "running" ? "text-blue-500" : "text-muted-foreground"}`}
                    >
                      {step.label}
                    </span>
                  </div>
                  <span
                    className={`text-[10px] px-1.5 py-0.5 rounded-full ${
                      step.status === "completed"
                        ? "bg-emerald-50 text-emerald-700"
                        : step.status === "running"
                          ? "bg-blue-50 text-blue-700"
                          : step.status === "failed"
                            ? "bg-red-50 text-red-700"
                            : "bg-muted text-muted-foreground/60"
                    }`}
                  >
                    {step.status === "completed"
                      ? "已完成"
                      : step.status === "running"
                        ? "分析中"
                        : step.status === "failed"
                          ? "失败"
                          : "等待中"}
                  </span>
                </div>
              ))}
            </div>
          ) : (
            // Select Items Form UI
            <>
              {items.map((item) => (
                <div
                  key={item.key}
                  className={`flex items-start gap-3 rounded-lg border p-3 cursor-pointer transition-colors ${
                    item.checked
                      ? "border-primary/50 bg-primary/5"
                      : "hover:bg-muted/50"
                  }`}
                  onClick={() => handleToggle(item.key)}
                >
                  <Checkbox
                    checked={item.checked}
                    onCheckedChange={() => handleToggle(item.key)}
                    className="mt-0.5"
                  />
                  <item.icon
                    className={`h-5 w-5 mt-0.5 shrink-0 ${item.checked ? "text-primary" : "text-muted-foreground"}`}
                  />
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2">
                      <span className="text-sm font-medium">{item.label}</span>
                      <span
                        className={`text-xs px-1.5 py-0.5 rounded-full ${
                          item.status === "completed"
                            ? "bg-green-100 text-green-700"
                            : item.status === "running"
                              ? "bg-blue-100 text-blue-700"
                              : "bg-muted text-muted-foreground"
                        }`}
                      >
                        {statusLabel(item.status)}
                      </span>
                    </div>
                    <p className="text-xs text-muted-foreground mt-0.5">
                      {item.desc}
                    </p>
                  </div>
                </div>
              ))}

              <div className="flex items-start gap-3 rounded-md border p-3 bg-muted/20">
                <Checkbox
                  id="record-secrets"
                  checked={recordSecrets}
                  onCheckedChange={(checked) =>
                    setRecordSecrets(checked === true)
                  }
                  className="mt-0.5"
                />
                <Shield className="h-5 w-5 mt-0.5 text-amber-500 shrink-0" />
                <div className="space-y-1 leading-none">
                  <label
                    htmlFor="record-secrets"
                    className="text-sm font-medium cursor-pointer flex items-center gap-1.5"
                  >
                    {t("generation.dialog.recordSecrets")}
                    <span className="text-xs text-amber-600 bg-amber-50 px-1.5 py-0.5 rounded">
                      {t("generation.dialog.recordSecretsWarning")}
                    </span>
                  </label>
                  <p className="text-xs text-muted-foreground">
                    {t("generation.dialog.recordSecretsDesc")}
                  </p>
                </div>
              </div>
            </>
          )}
        </div>

        <DialogFooter>
          {isAnalyzing ? (
            <Button onClick={() => onOpenChange(false)} disabled={!allFinished}>
              {allFinished ? "完成并关闭" : "正在生成分析中..."}
            </Button>
          ) : (
            <>
              <Button
                variant="outline"
                onClick={() => onOpenChange(false)}
                disabled={generating}
              >
                {t("generation.dialog.cancel")}
              </Button>
              <Button
                onClick={handleGenerate}
                disabled={
                  loading || generating || items.every((i) => !i.checked)
                }
              >
                {generating ? (
                  <Loader2 className="h-4 w-4 mr-1.5 animate-spin" />
                ) : null}
                {t("generation.dialog.generate", {
                  count: items.filter((i) => i.checked).length,
                })}
              </Button>
            </>
          )}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
