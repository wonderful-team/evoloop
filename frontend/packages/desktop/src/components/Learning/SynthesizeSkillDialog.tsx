import { Loader2, Sparkles, Info, Terminal, Settings2 } from "lucide-react"
import { useState } from "react"
import { useTranslation } from "react-i18next"
import { toast } from "sonner"
import { LearningService } from "@/client/sdk.gen"
import { Input } from "@evoloop/shared/components/ui/input"
import { Button } from "@evoloop/shared/components/ui/button"
import { Badge } from "@evoloop/shared/components/ui/badge"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@evoloop/shared/components/ui/dialog"

interface SynthesizeSkillDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  sessionId: string
  threadId: string
  onSuccess?: () => void
  onOpenEditor?: (skillId: number) => void
}

export function SynthesizeSkillDialog({
  open,
  onOpenChange,
  sessionId,
  threadId,
  onSuccess,
  onOpenEditor,
}: SynthesizeSkillDialogProps) {
  const { t } = useTranslation()
  const [isSynthesizing, setIsSynthesizing] = useState(false)
  const [result, setResult] = useState<{ id: number; name: string; description?: string; trigger_patterns?: string[]; parameters?: any[] } | null>(null)
  const [editedName, setEditedName] = useState("")
  const [autoOptimize, setAutoOptimize] = useState(true)
  const [isUpdating, setIsUpdating] = useState(false)

  const handleSynthesize = async () => {
    setIsSynthesizing(true)
    try {
      const response = (await LearningService.synthesizeSkill({
        requestBody: { thread_id: threadId, session_id: sessionId, auto_optimize: autoOptimize } as any,
      })) as any
      if (response.success) {
        toast.success(t("learning.synthesisSuccess", "Skill created successfully!"))
        setResult({
          id: response.skill_id,
          name: response.skill_name,
          description: response.description,
          trigger_patterns: response.trigger_patterns,
          parameters: response.parameters
        })
        setEditedName(response.skill_name)
        onSuccess?.()
      } else {
        toast.error(t("learning.synthesisFailed", "Failed to create skill"))
      }
    } catch (error) {
      console.error("Synthesis error:", error)
      toast.error(t("learning.synthesisError", "An error occurred during synthesis"))
    } finally {
      setIsSynthesizing(false)
    }
  }

  const handleSaveAndClose = async () => {
    if (result && editedName && editedName !== result.name) {
      setIsUpdating(true)
      try {
        await LearningService.updateSkill({
          skillId: result.id,
          requestBody: { name: editedName }
        })
        onSuccess?.()
      } catch (error) {
        console.error("Update error:", error)
        toast.error(t("common.error.message", "Failed to update"))
        setIsUpdating(false)
        return
      }
    }
    setResult(null); setEditedName(""); onOpenChange(false)
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <Sparkles className="h-5 w-5 text-yellow-500" />
            {result ? t("learning.skillCreated") : t("learning.createSkill")}
          </DialogTitle>
          <DialogDescription>
            {result ? t("learning.skillCreatedDesc") : t("learning.createSkillDesc")}
          </DialogDescription>
        </DialogHeader>

        {result ? (
          <div className="py-4 space-y-4">
            <div className="grid gap-2">
              <label className="text-[10px] font-bold uppercase text-muted-foreground">{t("learning.skillName")}</label>
              <Input value={editedName} onChange={(e) => setEditedName(e.target.value)} />
            </div>

            {result.description && (
              <div className="bg-muted/30 p-3 rounded-lg border border-dashed text-xs text-muted-foreground">
                <div className="flex items-center gap-1.5 font-bold mb-1 uppercase text-[10px]">
                  <Info className="h-3 w-3" /> {t("learning.editor.skillDescription")}
                </div>
                {result.description}
              </div>
            )}

            {result.trigger_patterns && result.trigger_patterns.length > 0 && (
              <div className="space-y-2">
                <div className="flex items-center gap-1.5 font-bold uppercase text-[10px] text-muted-foreground">
                  <Terminal className="h-3 w-3" /> {t("learning.editor.triggerPatterns")}
                </div>
                <div className="flex flex-wrap gap-1.5">
                  {result.trigger_patterns.map((tag, i) => (
                    <Badge key={i} variant="secondary" className="px-2 py-0 h-5 text-[10px] border">
                      {tag}
                    </Badge>
                  ))}
                </div>
              </div>
            )}

            {result.parameters && result.parameters.length > 0 && (
              <div className="space-y-2">
                <div className="flex items-center gap-1.5 font-bold uppercase text-[10px] text-muted-foreground">
                  <Settings2 className="h-3 w-3" /> {t("learning.editor.parameters")}
                </div>
                <div className="flex flex-wrap gap-1.5">
                  {result.parameters.map((p, i) => (
                    <Badge key={i} variant="outline" className="px-2 py-0 h-5 text-[10px] bg-primary/5">
                      {p.name} ({p.type})
                    </Badge>
                  ))}
                </div>
              </div>
            )}

            <div className="flex justify-center pt-2">
              <Button
                variant="outline"
                size="sm"
                className="w-full gap-2 text-xs h-8 border-primary/20 hover:border-primary/50 text-primary"
                onClick={() => {
                  onOpenEditor?.(result.id)
                  onOpenChange(false)
                }}
              >
                <Settings2 className="h-3.5 w-3.5" />
                {t("learning.centerSubtitle", "Open Full Editor")}
              </Button>
            </div>
          </div>
        ) : (
          <div className="py-4 space-y-4">
            <div className="text-sm text-muted-foreground bg-muted/20 p-4 rounded-xl border border-dashed text-center">
              {t("learning.synthesisPrompt")}
            </div>

            <div className="flex items-center justify-between px-1">
              <div className="space-y-0.5">
                <div className="text-[10px] font-bold uppercase flex items-center gap-1.5">
                  <Sparkles className="h-3 w-3 text-yellow-500" />
                  {t("learning.autoOptimize", "Auto-Optimize Steps")}
                </div>
                <div className="text-[10px] text-muted-foreground">
                  {t("learning.autoOptimizeDesc", "Remove redundant actions and streamline logic")}
                </div>
              </div>
              <Button
                variant={autoOptimize ? "default" : "outline"}
                size="sm"
                className="h-7 text-[10px] px-3"
                onClick={() => setAutoOptimize(!autoOptimize)}
              >
                {autoOptimize ? t("common.enabled") : t("common.disabled")}
              </Button>
            </div>
          </div>
        )}

        <DialogFooter>
          {result ? (
            <Button onClick={handleSaveAndClose} disabled={isUpdating} className="w-full">
              {isUpdating && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
              {t("common.saveAndClose")}
            </Button>
          ) : (
            <div className="flex w-full gap-2">
              <Button variant="outline" onClick={() => onOpenChange(false)} disabled={isSynthesizing} className="flex-1">
                {t("common.cancel")}
              </Button>
              <Button onClick={handleSynthesize} disabled={isSynthesizing} className="flex-1">
                {isSynthesizing ? <Loader2 className="h-4 w-4 animate-spin" /> : <Sparkles className="mr-2 h-4 w-4" />}
                {t("learning.synthesize")}
              </Button>
            </div>
          )}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
