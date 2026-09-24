import {Badge} from "@evoloop/shared/components/ui/badge"
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
import {Input} from "@evoloop/shared/components/ui/input"
import {Label} from "@evoloop/shared/components/ui/label"
import {ScrollArea} from "@evoloop/shared/components/ui/scroll-area"
import {Switch} from "@evoloop/shared/components/ui/switch"
import {Textarea} from "@evoloop/shared/components/ui/textarea"
import {AlertCircle, Loader2, Play} from "lucide-react"
import React, {useState} from "react"
import {useTranslation} from "react-i18next"
import {toast} from "sonner"
import {LearningService} from "@/client/sdk.gen"
import type {LearnedSkill} from "@/types/skill"
import {executeSkillErrorMessage} from "./skillLifecycle"

interface SkillExecutionDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  skill: LearnedSkill
  threadId: string
  projectId?: number
  onSuccess?: () => void
}

export function SkillExecutionDialog({
  open,
  onOpenChange,
  skill,
  threadId,
  projectId,
  onSuccess,
}: SkillExecutionDialogProps) {
  const { t } = useTranslation()
  const [params, setParams] = useState<Record<string, any>>({})
  const [executing, setExecuting] = useState(false)
  // Per-run self-heal toggle (defaults to the skill's declared setting)
  const [selfHealEnabled, setSelfHealEnabled] = useState(true)

  // Initialize defaults
  React.useEffect(() => {
    if (open && skill) {
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

      const pArr = safeParse(skill.parameters, [])
      const defaults: Record<string, any> = {}
      pArr.forEach((p: any) => {
        if (p.default !== undefined) {
          defaults[p.name] = p.default
        } else if (p.type === "boolean") {
          defaults[p.name] = false
        }
      })
      setParams(defaults)
      setSelfHealEnabled(skill.allow_self_healing !== false)
    }
  }, [open, skill])

  const handleExecute = async () => {
    setExecuting(true)
    try {
      await LearningService.runSkill({
        skillId: skill.id,
        requestBody: {
          thread_id: threadId,
          params: {
            ...params,
            _allow_self_healing: selfHealEnabled,
          },
          project_id: projectId,
        },
      })
      toast.success(t("learning.executionStarted"))
      onOpenChange(false)
      onSuccess?.()
    } catch (error) {
      console.error("Execution failed", error)
      toast.error(
        executeSkillErrorMessage(error) ?? t("learning.executionFailed"),
      )
    } finally {
      setExecuting(false)
    }
  }

  const renderInput = (param: any) => {
    const type = (param.type || "string").toLowerCase()
    const value = params[param.name] ?? ""

    if (type === "boolean") {
      return (
        <div className="flex items-center space-x-3 p-4 rounded-xl border bg-muted/20 transition-all hover:border-primary/30">
          <Checkbox
            id={`param-${param.name}`}
            checked={!!params[param.name]}
            onCheckedChange={(checked) =>
              setParams((prev) => ({ ...prev, [param.name]: checked }))
            }
          />
          <Label
            htmlFor={`param-${param.name}`}
            className="text-sm font-medium cursor-pointer flex-1"
          >
            {param.description || param.name}
          </Label>
        </div>
      )
    }

    if (type === "number" || type === "integer") {
      return (
        <Input
          id={`param - ${param.name} `}
          type="number"
          value={value}
          onChange={(e) =>
            setParams((prev) => ({
              ...prev,
              [param.name]:
                e.target.value === "" ? "" : parseFloat(e.target.value),
            }))
          }
          className="h-9"
          placeholder={param.default?.toString() || "0"}
        />
      )
    }

    if (type === "text" || type === "longstring") {
      return (
        <Textarea
          id={`param - ${param.name} `}
          value={value}
          onChange={(e) =>
            setParams((prev) => ({ ...prev, [param.name]: e.target.value }))
          }
          placeholder={param.default || "..."}
          rows={3}
          className="resize-none"
        />
      )
    }

    // Default string
    return (
      <Input
        id={`param-${param.name}`}
        value={value}
        onChange={(e) =>
          setParams((prev) => ({ ...prev, [param.name]: e.target.value }))
        }
        className="h-10 text-sm"
        placeholder={param.default || ""}
      />
    )
  }

  const safeParse = (data: any, defaultVal: any) => {
    if (!data) return defaultVal
    if (typeof data === "string") {
      try {
        return JSON.parse(data)
      } catch (_e) {
        return defaultVal
      }
    }
    return data
  }
  const pArr = safeParse(skill.parameters, [])

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-md p-0 overflow-hidden flex flex-col max-h-[85vh]">
        <DialogHeader className="p-6 pb-2">
          <DialogTitle className="flex items-center gap-2 text-xl font-bold">
            <Play className="h-5 w-5 text-primary" fill="currentColor" />
            {t("learning.execution.title", { name: skill.name })}
          </DialogTitle>
          <DialogDescription className="line-clamp-2">
            {skill.description || t("learning.execution.noParamsDescription")}
          </DialogDescription>
        </DialogHeader>

        <ScrollArea className="flex-1 px-6">
          <div className="space-y-6 py-4">
            {pArr.length > 0 ? (
              pArr.map((param: any) => (
                <div key={param.name} className="space-y-3">
                  {param.type !== "boolean" && (
                    <div className="flex items-center justify-between">
                      <Label
                        htmlFor={`param-${param.name}`}
                        className="text-xs font-bold uppercase text-muted-foreground flex items-center gap-2"
                      >
                        {param.description || param.name}
                        {param.required && (
                          <span className="text-destructive">*</span>
                        )}
                      </Label>
                      <Badge
                        variant="outline"
                        className="text-[9px] font-mono px-1.5 py-0 h-4 bg-muted/30 opacity-60"
                      >
                        {param.type}
                      </Badge>
                    </div>
                  )}
                  <div className="relative">{renderInput(param)}</div>
                  {param.description &&
                    param.type !== "boolean" &&
                    param.description !== param.name && (
                      <p className="text-[10px] text-muted-foreground opacity-70 px-1">
                        {t("learning.editor.paramName")}:{" "}
                        <span className="font-mono">{param.name}</span>
                      </p>
                    )}
                </div>
              ))
            ) : (
              <div className="flex flex-col items-center justify-center py-10 text-center space-y-3 bg-muted/20 rounded-2xl border border-dashed">
                <AlertCircle className="h-8 w-8 text-muted-foreground/30" />
                <div className="space-y-1">
                  <p className="text-sm font-medium">
                    {t("learning.execution.noParams")}
                  </p>
                  <p className="text-xs text-muted-foreground">
                    {t("learning.execution.description")}
                  </p>
                </div>
              </div>
            )}
          </div>
        </ScrollArea>

        <DialogFooter className="p-6 pt-2 border-t border-border mt-auto bg-muted/5">
          <label
            className="flex items-center gap-2 text-xs text-muted-foreground cursor-pointer select-none mr-auto"
            title={t("learning.selfHeal.toggleHint")}
          >
            <Switch
              checked={selfHealEnabled}
              onCheckedChange={setSelfHealEnabled}
              className="scale-90"
            />
            {t("learning.selfHeal.toggle")}
          </label>
          <Button
            variant="ghost"
            onClick={() => onOpenChange(false)}
            disabled={executing}
            className="text-xs"
          >
            {t("common.cancel")}
          </Button>
          <Button
            onClick={handleExecute}
            disabled={executing}
            className="min-w-[120px] gap-2 text-xs font-bold shadow-lg shadow-primary/20"
          >
            {executing ? (
              <>
                <Loader2 className="h-3.5 w-3.5 animate-spin" />
                {t("learning.execution.starting")}
              </>
            ) : (
              <>
                <Play className="h-3.5 w-3.5" fill="currentColor" />
                {t("learning.execution.runNow")}
              </>
            )}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
