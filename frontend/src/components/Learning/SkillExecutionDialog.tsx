
import React, { useState } from "react"
import { useTranslation } from "react-i18next"
import {
    Dialog,
    DialogContent,
    DialogDescription,
    DialogFooter,
    DialogHeader,
    DialogTitle,
} from "@/components/ui/dialog"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Textarea } from "@/components/ui/textarea"
import { Checkbox } from "@/components/ui/checkbox"
import { LearnedSkill, LearningService } from "@/client/LearningService"
import { toast } from "sonner"
import { Loader2, Play } from "lucide-react"

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
    onSuccess
}: SkillExecutionDialogProps) {
    const { t } = useTranslation()
    const [params, setParams] = useState<Record<string, any>>({})
    const [executing, setExecuting] = useState(false)

    // Initialize defaults
    React.useEffect(() => {
        if (open && skill.parameters) {
            const defaults: Record<string, any> = {}
            skill.parameters.forEach(p => {
                if (p.default !== undefined) {
                    defaults[p.name] = p.default
                } else if (p.type === 'boolean') {
                    defaults[p.name] = false
                }
            })
            setParams(defaults)
        }
    }, [open, skill])

    const handleExecute = async () => {
        setExecuting(true)
        try {
            await LearningService.executeSkill(skill.id, threadId, params, projectId)
            toast.success(t("learning.executionStarted", "Skill execution started"))
            onOpenChange(false)
            onSuccess?.()
        } catch (error) {
            console.error("Execution failed", error)
            toast.error(t("learning.executionFailed", "Failed to execute skill"))
        } finally {
            setExecuting(false)
        }
    }

    const renderInput = (param: any) => {
        const type = param.type.toLowerCase()
        const value = params[param.name] || ""

        if (type === 'boolean') {
            return (
                <div className="flex items-center space-x-2">
                    <Checkbox
                        id={`param-${param.name}`}
                        checked={!!params[param.name]}
                        onCheckedChange={(checked) => setParams(prev => ({ ...prev, [param.name]: checked }))}
                    />
                    <Label htmlFor={`param-${param.name}`}>{param.description || param.name}</Label>
                </div>
            )
        }

        if (type === 'number' || type === 'integer') {
            return (
                <Input
                    id={`param-${param.name}`}
                    type="number"
                    value={value}
                    onChange={(e) => setParams(prev => ({ ...prev, [param.name]: parseFloat(e.target.value) }))}
                    placeholder={param.default}
                />
            )
        }

        if (type === 'text' || type === 'longstring') {
            return (
                <Textarea
                    id={`param-${param.name}`}
                    value={value}
                    onChange={(e) => setParams(prev => ({ ...prev, [param.name]: e.target.value }))}
                    placeholder={param.default}
                    rows={3}
                />
            )
        }

        // Default string
        return (
            <Input
                id={`param-${param.name}`}
                value={value}
                onChange={(e) => setParams(prev => ({ ...prev, [param.name]: e.target.value }))}
                placeholder={param.default}
            />
        )
    }

    return (
        <Dialog open={open} onOpenChange={onOpenChange}>
            <DialogContent className="sm:max-w-md">
                <DialogHeader>
                    <DialogTitle className="flex items-center gap-2">
                        <Play className="h-4 w-4 text-green-500" />
                        Run Skill: {skill.name}
                    </DialogTitle>
                    <DialogDescription>
                        {skill.description || "Configure parameters to run this skill."}
                    </DialogDescription>
                </DialogHeader>

                <div className="space-y-4 py-4 max-h-[60vh] overflow-y-auto px-1">
                    {skill.parameters && skill.parameters.length > 0 ? (
                        skill.parameters.map((param) => (
                            <div key={param.name} className="space-y-2">
                                {param.type !== 'boolean' && (
                                    <Label htmlFor={`param-${param.name}`} className="flex items-baseline justify-between">
                                        <span>
                                            {param.name}
                                            {param.required && <span className="text-red-500 ml-1">*</span>}
                                        </span>
                                        <span className="text-xs text-muted-foreground font-normal bg-muted px-1.5 py-0.5 rounded">
                                            {param.type}
                                        </span>
                                    </Label>
                                )}
                                {renderInput(param)}
                                {param.type !== 'boolean' && param.description && (
                                    <p className="text-[11px] text-muted-foreground">{param.description}</p>
                                )}
                            </div>
                        ))
                    ) : (
                        <div className="text-center text-muted-foreground text-sm italic py-4">
                            No parameters required.
                        </div>
                    )}
                </div>

                <DialogFooter>
                    <Button variant="outline" onClick={() => onOpenChange(false)} disabled={executing}>
                        Cancel
                    </Button>
                    <Button onClick={handleExecute} disabled={executing} className="bg-green-600 hover:bg-green-700 text-white">
                        {executing ? (
                            <>
                                <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                                Starting...
                            </>
                        ) : (
                            <>
                                <Play className="mr-2 h-4 w-4" fill="currentColor" />
                                Run Now
                            </>
                        )}
                    </Button>
                </DialogFooter>
            </DialogContent>
        </Dialog>
    )
}
