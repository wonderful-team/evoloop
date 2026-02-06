import { Loader2, Sparkles, CheckCircle2 } from "lucide-react"
import { useState } from "react"
import { useTranslation } from "react-i18next"
import { toast } from "sonner"
import { LearningService } from "@/client/sdk.gen"
import { Input } from "@evoloop/shared/components/ui/input"
import { Button } from "@evoloop/shared/components/ui/button"
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
}

export function SynthesizeSkillDialog({
  open,
  onOpenChange,
  sessionId,
  threadId,
  onSuccess,
}: SynthesizeSkillDialogProps) {
  const { t } = useTranslation()
  const [isSynthesizing, setIsSynthesizing] = useState(false)
  const [result, setResult] = useState<{ id: number; name: string } | null>(null)
  const [editedName, setEditedName] = useState("")
  const [isUpdating, setIsUpdating] = useState(false)

  const handleSynthesize = async () => {
    setIsSynthesizing(true)
    try {
      const response = (await LearningService.synthesizeSkill({
        requestBody: { thread_id: threadId, session_id: sessionId },
      })) as any
      if (response.success) {
        toast.success(t("learning.synthesisSuccess", "Skill created successfully!"))
        setResult({ id: response.skill_id, name: response.skill_name })
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
    // If we have a result and name is edited and different, save first
    if (result && editedName && editedName !== result.name) {
      setIsUpdating(true)
      try {
        await LearningService.updateSkill({
          skillId: result.id,
          requestBody: { name: editedName }
        })
        toast.success(t("common.saved", "Saved"))
        onSuccess?.()
      } catch (error) {
        console.error("Update error:", error)
        toast.error(t("common.error.message", "Failed to update"))
        // Don't close if error? Or close anyway? Usually keep open to retry.
        setIsUpdating(false)
        return
      }
      setIsUpdating(false)
    }

    // Close dialog
    setResult(null)
    setEditedName("")
    onOpenChange(false)
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-[425px]">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <Sparkles className="h-5 w-5 text-yellow-500" />
            {result
              ? t("learning.skillCreated", "Skill Created!")
              : t("learning.createSkill", "Create Skill?")}
          </DialogTitle>
          <DialogDescription>
            {result
              ? t(
                "learning.skillCreatedDesc",
                "The skill has been added to your library.",
              )
              : t(
                "learning.createSkillDesc",
                "Analyze the recorded actions to create a reusable skill.",
              )}
          </DialogDescription>
        </DialogHeader>

        {result ? (
          <div className="py-4 space-y-4">
            <div className="rounded-md bg-muted p-4 space-y-2">
              <label className="text-sm font-medium text-muted-foreground">
                {t("learning.skillName", "Skill Name")}
              </label>
              <div className="flex gap-2">
                <Input
                  value={editedName}
                  onChange={(e) => setEditedName(e.target.value)}
                  className="bg-background w-full"
                />
              </div>
            </div>
            <p className="text-sm text-green-600 flex items-center gap-2">
              <CheckCircle2 className="h-4 w-4" />
              {t("learning.skillSaved", "Skill saved to library.")}
            </p>
          </div>
        ) : (
          <div className="py-4 text-sm text-muted-foreground">
            {t(
              "learning.synthesisPrompt",
              "This will use AI to analyze your actions and generate a parameterized skill that can be used later.",
            )}
          </div>
        )}

        <DialogFooter>
          {result ? (
            <Button onClick={handleSaveAndClose} disabled={isUpdating}>
              {isUpdating ? (
                <Loader2 className="mr-2 h-4 w-4 animate-spin" />
              ) : null}
              {editedName && result && editedName !== result.name
                ? t("common.saveAndClose", "Save & Close")
                : t("common.close", "Close")}
            </Button>
          ) : (
            <>
              <Button
                variant="outline"
                onClick={() => onOpenChange(false)}
                disabled={isSynthesizing}
              >
                {t("common.cancel", "Cancel")}
              </Button>
              <Button onClick={handleSynthesize} disabled={isSynthesizing}>
                {isSynthesizing ? (
                  <>
                    <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                    {t("learning.synthesizing", "Synthesizing...")}
                  </>
                ) : (
                  <>
                    <Sparkles className="mr-2 h-4 w-4" />
                    {t("learning.synthesize", "Synthesize Skill")}
                  </>
                )}
              </Button>
            </>
          )}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
