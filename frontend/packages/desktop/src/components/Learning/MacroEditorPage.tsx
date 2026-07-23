/**
 * MacroEditorPage - Full page macro script editor
 * Exposes a metadata editor sidebar and visual/yaml macro editors.
 * Now manages the self-healing switch and fallback recovery skill selection.
 */

import { Button } from "@evoloop/shared/components/ui/button"
import { Input } from "@evoloop/shared/components/ui/input"
import { Label } from "@evoloop/shared/components/ui/label"
import { Textarea } from "@evoloop/shared/components/ui/textarea"
import { Separator } from "@evoloop/shared/components/ui/separator"
import { Badge } from "@evoloop/shared/components/ui/badge"
import { Switch } from "@evoloop/shared/components/ui/switch"
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "@evoloop/shared/components/ui/tooltip"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { dump as yamlDump, load as yamlLoad } from "js-yaml"
import {
  ArrowLeft,
  HelpCircle,
  Loader2,
  Play,
  Save,
  Settings2,
  Trash2,
  Zap,
} from "lucide-react"
import { useCallback, useEffect, useState } from "react"
import { useTranslation } from "react-i18next"
import { toast } from "sonner"
import { MacrosService, SystemService } from "@/client/sdk.gen"
import { useChatStore } from "@/stores/chatStore"
import type { MacroDetailDTO } from "@/client/types.gen"
import type { MacroStep } from "./SmartReplay"
import { MacroEditor, MacroYamlEditor } from "./SmartReplay"

interface MacroEditorPageProps {
  macroId: number
  onBack?: () => void
  onSave?: () => void
}

function yamlToSteps(yaml: string): MacroStep[] {
  try {
    const parsed = yamlLoad(yaml || "steps: []")
    if (!parsed) return []
    if (Array.isArray(parsed)) return parsed as MacroStep[]
    if (typeof parsed === "object") {
      const obj = parsed as Record<string, unknown>
      if (Array.isArray(obj.steps)) return obj.steps as MacroStep[]
    }
    return []
  } catch {
    return []
  }
}

function stepsToYaml(steps: MacroStep[]): string {
  return yamlDump(steps, { indent: 2, lineWidth: -1, noRefs: true, sortKeys: false })
}

export function MacroEditorPage({
  macroId,
  onBack,
  onSave,
}: MacroEditorPageProps) {
  const { t } = useTranslation()
  const queryClient = useQueryClient()

  // Form state
  const [name, setName] = useState("")
  const [description, setDescription] = useState("")
  const [triggers, setTriggers] = useState("")
  const [steps, setSteps] = useState<MacroStep[]>([])
  const [editorMode, setEditorMode] = useState<"visual" | "yaml">("visual")
  const [selfHealEnabled, setSelfHealEnabled] = useState(false)
  const [globalSelfHealSupported, setGlobalSelfHealSupported] = useState(true)
  const [hasChanges, setHasChanges] = useState(false)

  // Fetch global config on mount
  useEffect(() => {
    let active = true
    const checkGlobalHealing = async () => {
      try {
        const status: any = await SystemService.getSystemStatus()
        if (active && status && status.enable_macro_self_healing === false) {
          setGlobalSelfHealSupported(false)
          setSelfHealEnabled(false)
        }
      } catch (err) {
        console.error("Failed to check global healing support:", err)
      }
    }
    checkGlobalHealing()
    return () => {
      active = false
    }
  }, [])

  // Fetch macro data
  const { data: macro, isLoading: isLoadingMacro } = useQuery({
    queryKey: ["macro", macroId],
    queryFn: async () => {
      const result = await MacrosService.getMacro({ macroId })
      return result as unknown as MacroDetailDTO
    },
  })

  // Track changes
  useEffect(() => {
    if (macro) {
      setHasChanges(true)
    }
  }, [name, description, triggers, steps, selfHealEnabled])

  // Warn before closing/leaving page with unsaved changes
  useEffect(() => {
    const handleBeforeUnload = (e: BeforeUnloadEvent) => {
      if (hasChanges) {
        e.preventDefault()
        e.returnValue = ""
        return ""
      }
    }
    window.addEventListener("beforeunload", handleBeforeUnload)
    return () => window.removeEventListener("beforeunload", handleBeforeUnload)
  }, [hasChanges])

  // Handle back button with unsaved changes
  const handleBack = useCallback(() => {
    if (hasChanges) {
      const confirmed = window.confirm(
        t("learning.editor.unsavedChangesConfirm"),
      )
      if (!confirmed) return
    }
    onBack?.()
  }, [hasChanges, onBack, t])

  // Initialize form from macro data
  useEffect(() => {
    if (macro) {
      setName(macro.name || "")
      setDescription(macro.description || "")
      setTriggers(
        Array.isArray(macro.trigger_patterns)
          ? macro.trigger_patterns.join("\n")
          : "",
      )
      setSteps(yamlToSteps(macro.macro_script))
      const hasHeal = macro.fallback_skill_id != null
      setSelfHealEnabled(hasHeal && globalSelfHealSupported)
      setHasChanges(false)
    }
  }, [macro, globalSelfHealSupported])

  // Mutations
  const updateMutation = useMutation({
    mutationFn: async () => {
      const triggerList = triggers
        .split("\n")
        .map((s) => s.trim())
        .filter(Boolean)

      return MacrosService.updateMacro({
        macroId,
        requestBody: {
          name,
          description,
          trigger_patterns: triggerList,
          macro_script: stepsToYaml(steps),
        },
      })
    },
    onSuccess: () => {
      toast.success(t("common.saved"))
      setHasChanges(false)
      queryClient.invalidateQueries({ queryKey: ["macros"] })
      queryClient.invalidateQueries({ queryKey: ["macro", macroId] })
      onSave?.()
    },
    onError: (error: any) => {
      toast.error(error.message || t("common.error.message"))
    },
  })

  const deleteMutation = useMutation({
    mutationFn: () => MacrosService.deleteMacro({ macroId }),
    onSuccess: () => {
      toast.success(t("learning.macros.deleted"))
      queryClient.invalidateQueries({ queryKey: ["macros"] })
      onBack?.()
    },
    onError: (error: any) => {
      toast.error(error.message || t("common.error.message"))
    },
  })

  const handleSave = async () => {
    if (!name.trim()) {
      toast.error(t("learning.editor.nameRequired"))
      return
    }
    updateMutation.mutate()
  }

  const handleRun = async () => {
    try {
      const threadId = useChatStore.getState().threadId
      if (!threadId) {
        toast.error(t("learning.macroRun.openChatFirst"))
        return
      }
      const executionParams: Record<string, unknown> = {
        _allow_self_healing: selfHealEnabled,
      }
      // Execute the macro deterministic run
      const r = await MacrosService.executeMacro({
        macroId,
        requestBody: {
          thread_id: threadId,
          params: executionParams,
        },
      }) as any
      if (r.success) {
        toast.success(r.message || t("learning.macros.runSuccess"))
      } else {
        toast.error(r.message || t("learning.macros.runFailed"))
      }
    } catch (e) {
      toast.error(t("learning.executionFailed"))
    }
  }

  const handleDelete = () => {
    if (window.confirm(t("common.deleteConfirm"))) {
      deleteMutation.mutate()
    }
  }

  if (isLoadingMacro) {
    return (
      <div className="flex items-center justify-center h-full">
        <Loader2 className="h-8 w-8 animate-spin text-primary" />
      </div>
    )
  }

  if (!macro) {
    return (
      <div className="flex flex-col items-center justify-center h-full gap-4">
        <p className="text-muted-foreground">{t("learning.macros.notFound")}</p>
        <Button onClick={handleBack}>
          <ArrowLeft className="h-4 w-4 mr-2" />
          {t("common.back")}
        </Button>
      </div>
    )
  }

  return (
    <div className="flex flex-col h-full bg-background">
      {/* Header */}
      <header className="flex items-center justify-between px-3 py-2 border-b bg-card shrink-0">
        <div className="flex items-center gap-4">
          <Button
            variant="ghost"
            size="sm"
            onClick={handleBack}
            className="gap-2"
          >
            <ArrowLeft className="h-4 w-4" />
            {t("common.back")}
          </Button>
          <Separator orientation="vertical" className="h-6" />
          <div className="flex items-center gap-3">
            <div className="p-2 bg-primary/10 rounded-xl">
              <Zap className="h-5 w-5 text-primary" />
            </div>
            <div>
              <h1 className="text-xl font-bold">{macro.name}</h1>
              <p className="text-xs text-muted-foreground">
                {t("learning.macros.editDesc")}
              </p>
            </div>
          </div>
        </div>

        <div className="flex items-center gap-3">
          <div className="flex items-center gap-2">
            <label
              className="flex items-center gap-2 text-xs text-muted-foreground cursor-pointer select-none"
            >
              <Switch
                checked={selfHealEnabled}
                onCheckedChange={setSelfHealEnabled}
                disabled={!globalSelfHealSupported}
                className="scale-90"
              />
              <span className={!globalSelfHealSupported ? "text-muted-foreground/60 line-through" : ""}>
                {t("learning.selfHeal.toggle")}
              </span>
              {!globalSelfHealSupported && (
                <span className="text-[10px] text-red-500 font-bold bg-red-500/10 px-1 rounded border border-red-500/20">
                  {t("learning.selfHeal.globallyDisabled")}
                </span>
              )}
            </label>

            <TooltipProvider>
              <Tooltip>
                <TooltipTrigger asChild>
                  <HelpCircle className="h-3.5 w-3.5 text-muted-foreground/50 hover:text-foreground cursor-help transition-colors" />
                </TooltipTrigger>
                <TooltipContent side="bottom" className="max-w-[260px] text-xs">
                  {globalSelfHealSupported
                    ? t("learning.selfHeal.toggleHint")
                    : t("learning.selfHeal.globallyDisabledHint")}
                </TooltipContent>
              </Tooltip>
            </TooltipProvider>
          </div>

          <Button
            variant="outline"
            size="sm"
            className="gap-2 text-xs font-bold border-emerald-500/20 text-emerald-600 hover:bg-emerald-50"
            onClick={handleRun}
            disabled={updateMutation.isPending}
          >
            <Play className="h-3.5 w-3.5 fill-current" />
            {t("learning.execution.runNow")}
          </Button>

          <Button
            variant="ghost"
            size="sm"
            className="gap-2 text-destructive hover:bg-destructive/10"
            onClick={handleDelete}
            disabled={deleteMutation.isPending}
          >
            <Trash2 className="h-4 w-4" />
            {t("common.delete")}
          </Button>

          <Separator orientation="vertical" className="h-6" />

          <Button
            onClick={handleSave}
            disabled={updateMutation.isPending}
            className="gap-2 px-6 font-bold shadow-lg shadow-primary/20 transition-all hover:scale-[1.02] active:scale-[0.98]"
          >
            {updateMutation.isPending ? (
              <Loader2 className="h-4 w-4 animate-spin" />
            ) : (
              <Save className="h-4 w-4" />
            )}
            {t("learning.editor.saveChanges")}
          </Button>
        </div>
      </header>

      {/* Main Content */}
      <div className="flex-1 flex overflow-hidden">
        {/* Sidebar Configuration */}
        <div className="w-[360px] border-r border-border flex flex-col bg-muted/5 p-5 gap-5 overflow-y-auto shrink-0">
          <div className="h-[24px] flex items-center gap-2 shrink-0">
            <Settings2 className="h-4 w-4 text-primary" />
            <span className="text-[11px] font-bold uppercase tracking-widest text-muted-foreground/80">
              {t("learning.editor.configSidebar")}
            </span>
          </div>

          <div className="space-y-2">
            <Label className="text-xs font-bold">{t("common.name")}</Label>
            <Input
              value={name}
              onChange={(e) => setName(e.target.value)}
              className="text-sm bg-background"
            />
          </div>

          <div className="space-y-2">
            <Label className="text-xs font-bold">{t("learning.editor.skillDescription")}</Label>
            <Textarea
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              className="text-sm bg-background resize-none"
              rows={4}
            />
          </div>

          <Separator />

          <div className="space-y-2">
            <Label className="text-xs font-bold">
              {t("learning.macros.triggerPatterns")}
            </Label>
            <p className="text-[11px] text-muted-foreground leading-normal">
              {t("learning.macros.triggerPatternsHint")}
            </p>
            <Textarea
              value={triggers}
              onChange={(e) => setTriggers(e.target.value)}
              className="text-sm font-mono bg-background resize-none"
              rows={6}
              placeholder="e.g. 查询余额\n查看账户余额"
            />
          </div>

          <div className="space-y-2">
            <Label className="text-xs font-bold">{t("learning.macros.riskTier")}</Label>
            <div>
              <Badge variant="outline" className="font-mono text-sm px-2.5 py-0.5">
                {macro.risk_tier}
              </Badge>
            </div>
            <p className="text-[11px] text-muted-foreground leading-normal pt-1">
              {t("learning.macros.riskTierHint")}
            </p>
          </div>
        </div>

        {/* Visual / YAML Editor Area */}
        <div className="flex-1 p-3 flex flex-col bg-muted/10 h-full min-h-0">
          <div className="flex flex-row items-center justify-between mb-2 shrink-0">
            <div className="flex items-center gap-2 text-sm font-bold text-emerald-600">
              <Zap className="h-4 w-4" />
              <span>
                {editorMode === "visual"
                  ? t("learning.macroSequence") + " (Visual)"
                  : t("learning.macroSequence") + " (YAML)"}
              </span>
            </div>
            <div className="flex items-center gap-2">
              <div className="flex items-center gap-1 text-xs bg-background p-1 rounded-md border shadow-sm">
                <button
                  onClick={() => setEditorMode("visual")}
                  className={`px-3 py-1.5 rounded-sm transition-colors text-xs font-bold ${
                    editorMode === "visual"
                      ? "bg-emerald-100 text-emerald-800"
                      : "hover:bg-muted text-muted-foreground"
                  }`}
                >
                  {t("macroEditor.visual")}
                </button>
                <button
                  onClick={() => setEditorMode("yaml")}
                  className={`px-3 py-1.5 rounded-sm transition-colors text-xs font-bold ${
                    editorMode === "yaml"
                      ? "bg-emerald-100 text-emerald-800"
                      : "hover:bg-muted text-muted-foreground"
                  }`}
                >
                  YAML
                </button>
              </div>
            </div>
          </div>

          <div className="flex-1 min-h-0 border rounded-xl bg-background shadow-sm overflow-hidden">
            {editorMode === "visual" ? (
              <MacroEditor
                steps={steps}
                onChange={setSteps}
                onStepPreview={(step) => {
                  console.log("Preview step:", step)
                  toast.info(
                    t("learning.stepPreview", {
                      number: step.step_number,
                      description: step.description || step.event_type,
                    }),
                  )
                }}
              />
            ) : (
              <MacroYamlEditor
                steps={steps}
                onChange={setSteps}
              />
            )}
          </div>
        </div>
      </div>
    </div>
  )
}
