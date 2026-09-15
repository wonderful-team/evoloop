/**
 * SkillEditorPage - Full page skill editor for agentic SOP skills only.
 * Macro script editing has been moved to MacroLibraryView / MacroEditDialog.
 */

import { Button } from "@evoloop/shared/components/ui/button"
import { Separator } from "@evoloop/shared/components/ui/separator"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import {
  ArrowLeft,
  Loader2,
  Play,
  Save,
  Settings2,
  Sparkles,
  Trash2,
} from "lucide-react"
import { useCallback, useEffect, useState } from "react"
import { useTranslation } from "react-i18next"
import { toast } from "sonner"
import { LearningService } from "@/client/sdk.gen"
import { MarkdownEditor } from "@/components/Common/MarkdownEditor"
import { useChatStore } from "@/stores/chatStore"
import type { LearnedSkill } from "@/types/skill"
import type { ParamDef } from "./EditorSidebar"
import { EditorSidebar } from "./EditorSidebar"
import { MacroRunFeed } from "./MacroRunFeed"
import { executeSkillErrorMessage } from "./skillLifecycle"

interface SkillEditorPageProps {
  skillId: number
  onBack?: () => void
  onSave?: () => void
}

export function SkillEditorPage({
  skillId,
  onBack,
  onSave,
}: SkillEditorPageProps) {
  const { t } = useTranslation()
  const queryClient = useQueryClient()

  // Form state
  const [name, setName] = useState("")
  const [description, setDescription] = useState("")
  const [triggers, setTriggers] = useState<string[]>([])
  const [newTrigger, setNewTrigger] = useState("")
  const [params, setParams] = useState<ParamDef[]>([])
  const [instructions, setInstructions] = useState("")
  const [hasChanges, setHasChanges] = useState(false)

  // Fetch skill data
  const { data: skill, isLoading: isLoadingSkill } = useQuery({
    queryKey: ["skill", skillId],
    queryFn: async () => {
      const result = await LearningService.getSkill({ skillId })
      return result as unknown as LearnedSkill
    },
  })

  // Track changes
  useEffect(() => {
    if (skill) {
      setHasChanges(true)
    }
  }, [name, description, triggers, params, instructions])

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

  // Initialize form from skill data
  useEffect(() => {
    if (skill) {
      const safeParse = (data: any, defaultVal: any) => {
        if (!data) return defaultVal
        if (typeof data === "string") {
          try {
            return JSON.parse(data)
          } catch (e) {
            console.error("Failed to parse", data, e)
            return defaultVal
          }
        }
        return data
      }

      setName(skill.name || "")
      setDescription(skill.description || "")
      setTriggers(safeParse(skill.trigger_patterns, []))
      setParams(safeParse(skill.parameters, []))
      setInstructions(skill.instructions || "")
      setHasChanges(false)
    }
  }, [skill])

  // Mutations
  const updateMutation = useMutation({
    mutationFn: async () => {
      return LearningService.updateSkill({
        skillId,
        requestBody: {
          name,
          description,
          trigger_patterns: triggers,
          parameters: params as any[],
          instructions: instructions,
        } as any,
      })
    },
    onSuccess: () => {
      toast.success(t("common.saved"))
      setHasChanges(false)
      queryClient.invalidateQueries({ queryKey: ["learnedSkills"] })
      queryClient.invalidateQueries({ queryKey: ["skill", skillId] })
      onSave?.()
    },
    onError: (error: any) => {
      toast.error(error.message || t("common.error.message"))
    },
  })

  const deleteMutation = useMutation({
    mutationFn: () => (LearningService as any).deleteSkill({ skillId }),
    onSuccess: () => {
      toast.success(t("common.success"))
      queryClient.invalidateQueries({ queryKey: ["learnedSkills"] })
      onBack?.()
    },
    onError: (error: any) => {
      toast.error(error.message || t("common.error.message"))
    },
  })

  // Form handlers
  const handleAddTrigger = () => {
    if (!newTrigger.trim()) return
    if (triggers.includes(newTrigger.trim())) {
      setNewTrigger("")
      return
    }
    setTriggers([...triggers, newTrigger.trim()])
    setNewTrigger("")
  }

  const handleRemoveTrigger = (index: number) => {
    setTriggers(triggers.filter((_, i) => i !== index))
  }

  const handleAddParam = () => {
    setParams([...params, { name: "", type: "string", description: "" }])
  }

  const handleRemoveParam = (index: number) => {
    setParams(params.filter((_, i) => i !== index))
  }

  const handleParamChange = (
    index: number,
    field: keyof ParamDef,
    value: string,
  ) => {
    const newParams = [...params]
    newParams[index] = { ...newParams[index], [field]: value }
    setParams(newParams)
  }

  const handleSave = async () => {
    if (!name.trim()) {
      toast.error(t("learning.editor.nameRequired"))
      return
    }

    for (const p of params) {
      if (!p.name.trim()) {
        toast.error(t("learning.editor.paramNameRequired"))
        return
      }
      if (/\s/.test(p.name)) {
        toast.error(t("learning.editor.paramNameNoSpaces"))
        return
      }
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
      await LearningService.runSkill({
        skillId,
        requestBody: {
          thread_id: threadId,
          params: {},
        },
      })
      toast.success(t("learning.executionStarted"))
    } catch (e) {
      toast.error(executeSkillErrorMessage(e) ?? t("learning.executionFailed"))
    }
  }

  const handleDelete = () => {
    deleteMutation.mutate()
  }

  if (isLoadingSkill) {
    return (
      <div className="flex items-center justify-center h-full">
        <Loader2 className="h-8 w-8 animate-spin text-primary" />
      </div>
    )
  }

  if (!skill) {
    return (
      <div className="flex flex-col items-center justify-center h-full gap-4">
        <p className="text-muted-foreground">{t("learning.skillNotFound")}</p>
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
              <Settings2 className="h-5 w-5 text-primary" />
            </div>
            <div>
              <h1 className="text-xl font-bold">{skill.name}</h1>
              <p className="text-xs text-muted-foreground">
                {t("learning.editor.description")}
              </p>
            </div>
          </div>
        </div>

        <div className="flex items-center gap-3">
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

      <MacroRunFeed />

      {/* Main Content */}
      <div className="flex-1 flex overflow-hidden">
        <EditorSidebar
          name={name}
          setName={setName}
          description={description}
          setDescription={setDescription}
          triggers={triggers}
          newTrigger={newTrigger}
          setNewTrigger={setNewTrigger}
          handleAddTrigger={handleAddTrigger}
          handleRemoveTrigger={handleRemoveTrigger}
          params={params}
          handleAddParam={handleAddParam}
          handleRemoveParam={handleRemoveParam}
          handleParamChange={handleParamChange}
        />

        <div className="flex-1 p-3 flex flex-col bg-muted/10 h-full min-h-0">
          <div className="flex flex-row items-center justify-between mb-2 shrink-0">
            <div className="flex items-center gap-2 text-sm font-bold text-amber-600">
              <Sparkles className="h-4 w-4" />
              <span>{t("learning.expertGuide")}</span>
            </div>
          </div>
          <MarkdownEditor
            value={instructions}
            onChange={setInstructions}
            placeholder={t("learning.editor.expertGuidePlaceholder")}
          />
        </div>
      </div>
    </div>
  )
}
