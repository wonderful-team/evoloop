import { Loader2, Save } from "lucide-react"
import { useEffect, useState } from "react"
import { useTranslation } from "react-i18next"
import { toast } from "sonner"
import { LearningService } from "@/client/sdk.gen"
import { Button } from "@/components/ui/button"
import {
    Dialog,
    DialogContent,
    DialogDescription,
    DialogFooter,
    DialogHeader,
    DialogTitle,
} from "@/components/ui/dialog"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Textarea } from "@/components/ui/textarea"
import type { LearnedSkill } from "@/types/skill"

interface SkillEditorDialogProps {
    open: boolean
    onOpenChange: (open: boolean) => void
    skill: LearnedSkill
    onSuccess: () => void
}

export function SkillEditorDialog({
    open,
    onOpenChange,
    skill,
    onSuccess,
}: SkillEditorDialogProps) {
    const { t } = useTranslation()
    const [loading, setLoading] = useState(false)
    const [formData, setFormData] = useState({
        name: "",
        description: "",
        trigger_patterns: "", // Comma separated
        parameters_json: "", // JSON string
    })

    useEffect(() => {
        if (open && skill) {
            setFormData({
                name: skill.name,
                description: skill.description,
                trigger_patterns: (skill.trigger_patterns || []).join(", "),
                parameters_json: JSON.stringify(skill.parameters || [], null, 2),
            })
        }
    }, [open, skill])

    const handleSave = async () => {
        setLoading(true)
        try {
            // Validate JSON
            let parameters = []
            try {
                parameters = JSON.parse(formData.parameters_json)
            } catch (e) {
                toast.error(t("learning.editor.invalidJson"))
                setLoading(false)
                return
            }

            await LearningService.updateSkill({
                skillId: skill.id,
                requestBody: {
                    name: formData.name,
                    description: formData.description,
                    trigger_patterns: formData.trigger_patterns
                        .split(",")
                        .map((s) => s.trim())
                        .filter((s) => s),
                    parameters: parameters,
                },
            })

            toast.success(t("common.saved", "Skill updated successfully"))
            onSuccess()
            onOpenChange(false)
        } catch (error: any) {
            console.error("Failed to update skill", error)
            toast.error(error.message || t("common.error.message"))
        } finally {
            setLoading(false)
        }
    }

    return (
        <Dialog open={open} onOpenChange={onOpenChange}>
            <DialogContent className="sm:max-w-[600px]">
                <DialogHeader>
                    <DialogTitle>{t("learning.editor.title", { name: skill.name })}</DialogTitle>
                    <DialogDescription>
                        {t("learning.editor.description")}
                    </DialogDescription>
                </DialogHeader>

                <div className="grid gap-4 py-4">
                    <div className="grid gap-2">
                        <Label htmlFor="name">{t("learning.editor.skillName")}</Label>
                        <Input
                            id="name"
                            value={formData.name}
                            onChange={(e) =>
                                setFormData({ ...formData, name: e.target.value })
                            }
                        />
                    </div>

                    <div className="grid gap-2">
                        <Label htmlFor="description">{t("learning.editor.skillDescription")}</Label>
                        <Textarea
                            id="description"
                            value={formData.description}
                            onChange={(e) =>
                                setFormData({ ...formData, description: e.target.value })
                            }
                        />
                    </div>

                    <div className="grid gap-2">
                        <Label htmlFor="triggers">
                            {t("learning.editor.triggerPatterns")}
                        </Label>
                        <Textarea
                            id="triggers"
                            value={formData.trigger_patterns}
                            onChange={(e) =>
                                setFormData({ ...formData, trigger_patterns: e.target.value })
                            }
                            placeholder="e.g. check system health, uptime check"
                        />
                        <p className="text-xs text-muted-foreground">
                            {t("learning.editor.triggerHelp")}
                        </p>
                    </div>

                    <div className="grid gap-2">
                        <Label htmlFor="params">{t("learning.editor.parameters")}</Label>
                        <Textarea
                            id="params"
                            className="font-mono text-xs"
                            rows={8}
                            value={formData.parameters_json}
                            onChange={(e) =>
                                setFormData({ ...formData, parameters_json: e.target.value })
                            }
                        />
                    </div>
                </div>

                <DialogFooter>
                    <Button
                        variant="outline"
                        onClick={() => onOpenChange(false)}
                        disabled={loading}
                    >
                        {t("common.cancel")}
                    </Button>
                    <Button onClick={handleSave} disabled={loading}>
                        {loading ? (
                            <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                        ) : (
                            <Save className="mr-2 h-4 w-4" />
                        )}
                        {t("learning.editor.saveChanges")}
                    </Button>
                </DialogFooter>
            </DialogContent>
        </Dialog>
    )
}
