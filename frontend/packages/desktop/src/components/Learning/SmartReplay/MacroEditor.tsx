/**
 * MacroEditor - Visual editor for macro scripts
 *
 * Features:
 * - Drag-and-drop step reordering
 * - Visual step editing with form fields
 * - Step preview with video sync
 * - Add/remove step functionality
 */

import { useState, useCallback, useEffect, useMemo } from "react"
import * as LucideIcons from "lucide-react"
import {
    GripVertical,
    Trash2,
    Plus,
    ChevronDown,
    ChevronRight,
    Play,
    Copy,
    MousePointerClick,
    Undo2,
    Split,
    Repeat,
    Settings2,
} from "lucide-react"

import { Button } from "@evoloop/shared/components/ui/button"
import { Input } from "@evoloop/shared/components/ui/input"
import { Textarea } from "@evoloop/shared/components/ui/textarea"
import { Badge } from "@evoloop/shared/components/ui/badge"
import { Label } from "@evoloop/shared/components/ui/label"
import {
    Select,
    SelectContent,
    SelectItem,
    SelectTrigger,
    SelectValue,
} from "@evoloop/shared/components/ui/select"
import {
    Dialog,
    DialogContent,
    DialogHeader,
    DialogTitle,
    DialogTrigger,
} from "@evoloop/shared/components/ui/dialog"
import {
    Tooltip,
    TooltipContent,
    TooltipProvider,
    TooltipTrigger,
} from "@evoloop/shared/components/ui/tooltip"
import { useTranslation } from "react-i18next"
import { cn } from "@evoloop/shared/lib/utils"

// Macro step types
export interface MacroStep {
    step_number: number
    type: "action" | "extract" | "dump" | "wait" | "if" | "loop" | "control"
    source: "dom" | "mobile" | "desktop" | "hybrid" | "global"
    event_type?: string
    selector?: string
    selector_type?: "css" | "xpath" | "text" | "id"
    payload?: Record<string, any>
    url?: string
    wait_condition?: string
    timeout_ms?: number
    description?: string
    // Control flow
    condition?: {
        type: string
        target_selector?: string
        params?: Record<string, any>
    }
    then_steps?: MacroStep[]
    else_steps?: MacroStep[]
    steps?: MacroStep[]
    max_iterations?: number
}

interface MacroEditorProps {
    steps: MacroStep[]
    videoPath?: string
    onChange: (steps: MacroStep[]) => void
    onStepPreview?: (step: MacroStep, timestampMs?: number) => void
    readOnly?: boolean
}

// Interface for Registry Actions from Backend
export interface ActionDef {
    id: string
    platforms: string[]
    icon: string
    description: string
    zh: string
    en: string
    params: Record<string, string>
}

export function MacroEditor({
    steps,
    videoPath,
    onChange,
    onStepPreview,
    readOnly = false,
}: MacroEditorProps) {
    const { t, i18n } = useTranslation()
    const [actionRegistry, setActionRegistry] = useState<ActionDef[]>([])
    const [expandedSteps, setExpandedSteps] = useState<Set<number>>(new Set([0]))
    const [draggingIndex, setDraggingIndex] = useState<number | null>(null)
    const [originalSteps] = useState<MacroStep[]>(JSON.parse(JSON.stringify(steps)))

    // Fetch Action Registry from Backend
    useEffect(() => {
        fetch("/api/v1/learning/capabilities/actions")
            .then(res => res.json())
            .then(data => setActionRegistry(data))
            .catch(err => console.error("Failed to fetch Action Registry:", err))
    }, [])

    // Dynamically compute eventTypes from Registry
    const eventTypes = useMemo(() => {
        const groups: Record<string, { value: string; icon: React.ReactNode; label: string }[]> = {
            dom: [],
            mobile: [],
            desktop: [],
            global: []
        }

        actionRegistry.forEach(action => {
            // Map Lucide icon string to Component
            const IconComponent = (LucideIcons as any)[action.icon] || MousePointerClick
            const icon = <IconComponent className="h-4 w-4" />

            // Dynamic label based on locale
            const label = i18n.language === "zh" ? action.zh : action.en

            action.platforms.forEach(p => {
                if (groups[p]) {
                    groups[p].push({ value: action.id, icon, label })
                }
            })
        })

        // Merge "global" actions into all lists
        groups.global.forEach(action => {
            Object.keys(groups).forEach(p => {
                if (p !== "global") {
                    groups[p].push(action)
                }
            })
        })

        return groups
    }, [actionRegistry, i18n.language])

    // Toggle step expansion
    const toggleStep = useCallback((index: number) => {
        setExpandedSteps((prev) => {
            const next = new Set(prev)
            if (next.has(index)) {
                next.delete(index)
            } else {
                next.add(index)
            }
            return next
        })
    }, [])

    // Update a step field
    const updateStep = useCallback((index: number, updates: Partial<MacroStep>) => {
        const updated = [...steps]
        updated[index] = { ...updated[index], ...updates }
        onChange(updated)
    }, [steps, onChange])

    // Delete a step
    const deleteStep = useCallback((index: number) => {
        const updated = steps.filter((_, i) => i !== index)
        // Renumber steps
        updated.forEach((step, i) => {
            step.step_number = i + 1
        })
        onChange(updated)
    }, [steps, onChange])

    // Add a new step
    const addStep = useCallback((afterIndex?: number) => {
        const newStep: MacroStep = {
            step_number: 0,
            type: "action",
            source: "dom",
            event_type: "click",
            selector: "",
            selector_type: "css",
            description: t("macroEditor.newStep"),
        }

        let updated: MacroStep[]
        if (afterIndex !== undefined) {
            updated = [...steps]
            updated.splice(afterIndex + 1, 0, newStep)
        } else {
            updated = [...steps, newStep]
        }

        // Renumber steps
        updated.forEach((step, i) => {
            step.step_number = i + 1
        })

        onChange(updated)
        setExpandedSteps((prev) => new Set([...prev, updated.length - 1]))
    }, [steps, onChange])

    // Duplicate a step
    const duplicateStep = useCallback((index: number) => {
        const stepToCopy = { ...steps[index] }
        const updated = [...steps]
        updated.splice(index + 1, 0, stepToCopy)

        // Renumber steps
        updated.forEach((step, i) => {
            step.step_number = i + 1
        })

        onChange(updated)
    }, [steps, onChange])

    // Handle drag start
    const handleDragStart = useCallback((index: number) => {
        setDraggingIndex(index)
    }, [])

    // Handle drag over
    const handleDragOver = useCallback((e: React.DragEvent, index: number) => {
        e.preventDefault()
        if (draggingIndex === null || draggingIndex === index) return

        const updated = [...steps]
        const [draggedStep] = updated.splice(draggingIndex, 1)
        updated.splice(index, 0, draggedStep)

        // Renumber steps
        updated.forEach((step, i) => {
            step.step_number = i + 1
        })

        setDraggingIndex(index)
        onChange(updated)
    }, [draggingIndex, steps, onChange])

    // Handle drag end
    const handleDragEnd = useCallback(() => {
        setDraggingIndex(null)
    }, [])

    // Reset to original
    const handleReset = useCallback(() => {
        onChange(JSON.parse(JSON.stringify(originalSteps)))
    }, [originalSteps, onChange])

    // Get step icon
    const getStepIcon = useCallback((step: MacroStep) => {
        if (step.type === "if") return <Split className="h-4 w-4" />
        if (step.type === "loop") return <Repeat className="h-4 w-4" />
        if (step.type === "control") return <Settings2 className="h-4 w-4" />

        // Explicit icon mappings for common actions
        const actionIconMap: Record<string, React.ReactNode> = {
            click: <MousePointerClick className="h-4 w-4" />,
            navigate: <LucideIcons.Globe className="h-4 w-4" />,
            back: <LucideIcons.ArrowLeft className="h-4 w-4" />,
            input: <LucideIcons.Type className="h-4 w-4" />,
            key_press: <LucideIcons.Keyboard className="h-4 w-4" />,
            wait: (LucideIcons.Timer ? <LucideIcons.Timer className="h-4 w-4" /> : <LucideIcons.Clock className="h-4 w-4" />)
        }

        const eventTypeForIcon = step.event_type || (step.type === "wait" ? "wait" : "");
        if (actionIconMap[eventTypeForIcon]) {
            return actionIconMap[eventTypeForIcon];
        }

        const sourceEvents = (eventTypes as any)[step.source] || eventTypes.dom
        let foundEvent = sourceEvents.find((e: any) => e.value === step.event_type)

        // Fallback to global list if not found in current source
        if (!foundEvent && eventTypes.global) {
            foundEvent = eventTypes.global.find((e: any) => e.value === step.event_type)
        }

        return foundEvent?.icon || <MousePointerClick className="h-4 w-4" />
    }, [eventTypes])

    // Get step color
    const getStepColor = useCallback((step: MacroStep) => {
        switch (step.type) {
            case "extract":
                return "bg-blue-500/10 border-blue-500/30 text-blue-600"
            case "action":
                return step.event_type === "navigate"
                    ? "bg-purple-500/10 border-purple-500/30 text-purple-600"
                    : "bg-green-500/10 border-green-500/30 text-green-600"
            case "wait":
                return "bg-amber-500/10 border-amber-500/30 text-amber-600"
            case "if":
                return "bg-cyan-500/10 border-cyan-500/30 text-cyan-600"
            case "loop":
                return !step.payload?.items_key
                    ? "bg-rose-500/10 border-rose-500/30 text-rose-600"
                    : "bg-orange-500/10 border-orange-500/30 text-orange-600"
            case "control":
                return "bg-slate-500/10 border-slate-500/30 text-slate-600"
            default:
                return "bg-gray-500/10 border-gray-500/30 text-gray-600"
        }
    }, [])

    return (
        <TooltipProvider>
            <div className="flex flex-col h-full">
                {/* Toolbar */}
                {!readOnly && (
                    <div className="flex items-center justify-between p-2 border-b bg-muted/30">
                        <div className="flex items-center gap-2">
                            <span className="text-sm text-muted-foreground">
                                {t("macroEditor.steps", { count: steps.length })}
                            </span>
                            <div className="w-px h-4 bg-border mx-2" />
                            <Badge variant="outline" className="text-xs">
                                {t("macroEditor.actions", { count: steps.filter((s) => s.type === "action").length })}
                            </Badge>
                            <Badge variant="outline" className="text-xs bg-blue-500/10">
                                {t("macroEditor.extracts", { count: steps.filter((s) => s.type === "extract").length })}
                            </Badge>
                            <Badge variant="outline" className="text-xs bg-amber-500/10">
                                {t("macroEditor.waits", { count: steps.filter((s) => s.type === "wait").length })}
                            </Badge>
                        </div>
                        <div className="flex items-center gap-1">
                            <Tooltip>
                                <TooltipTrigger asChild>
                                    <Button
                                        variant="ghost"
                                        size="sm"
                                        onClick={handleReset}
                                    >
                                        <Undo2 className="h-4 w-4 mr-1" />
                                        {t("macroEditor.reset")}
                                    </Button>
                                </TooltipTrigger>
                                <TooltipContent>{t("macroEditor.resetTooltip")}</TooltipContent>
                            </Tooltip>
                            <Tooltip>
                                <TooltipTrigger asChild>
                                    <Button
                                        variant="ghost"
                                        size="sm"
                                        onClick={() => addStep()}
                                    >
                                        <Plus className="h-4 w-4 mr-1" />
                                        {t("macroEditor.addStep")}
                                    </Button>
                                </TooltipTrigger>
                                <TooltipContent>{t("macroEditor.addStepTooltip")}</TooltipContent>
                            </Tooltip>
                        </div>
                    </div>
                )}

                {/* Steps list */}
                <div className="flex-1 overflow-auto p-2 space-y-2">
                    {steps.map((step, index) => (
                        <div
                            key={`${index}-${step.step_number}`}
                            draggable={!readOnly}
                            onDragStart={() => handleDragStart(index)}
                            onDragOver={(e) => handleDragOver(e, index)}
                            onDragEnd={handleDragEnd}
                            className={cn(
                                "border rounded-lg overflow-hidden transition-all",
                                draggingIndex === index && "opacity-50 ring-2 ring-primary",
                                expandedSteps.has(index) && "ring-1 ring-border"
                            )}
                        >
                            {/* Step header */}
                            <div
                                className={cn(
                                    "flex items-center gap-2 p-3 cursor-pointer hover:bg-muted/50 transition-colors group",
                                    getStepColor(step)
                                )}
                                onClick={() => toggleStep(index)}
                            >
                                {!readOnly && (
                                    <div className="cursor-grab active:cursor-grabbing">
                                        <GripVertical className="h-4 w-4 text-muted-foreground" />
                                    </div>
                                )}

                                {expandedSteps.has(index) ? (
                                    <ChevronDown className="h-4 w-4" />
                                ) : (
                                    <ChevronRight className="h-4 w-4" />
                                )}

                                <div className="flex items-center justify-center w-6 h-6 rounded bg-background/80 text-xs font-mono">
                                    {step.step_number}
                                </div>

                                <div className="p-1.5 rounded bg-background/80">
                                    {getStepIcon(step)}
                                </div>

                                <Badge variant="secondary" className="text-xs capitalize">
                                    {(() => {
                                        const commonActions = ["click", "navigate", "input", "key_press", "wait"];
                                        if (step.type === "action" && commonActions.includes(step.event_type || "")) {
                                            return t(`macroEditor.eventTypes.${step.event_type}`);
                                        }
                                        return step.event_type
                                            ? t(`macroEditor.eventTypes.${step.event_type}`)
                                            : t(`macroEditor.stepTypes.${step.type}`);
                                    })()}
                                </Badge>

                                <span className="flex-1 truncate text-sm">
                                    {step.description || step.selector || t("macroEditor.noDescription")}
                                </span>

                                <Badge variant="outline" className="text-xs">
                                    {t(`macroEditor.sources.${step.source}`)}
                                </Badge>

                                {!readOnly && (
                                    <div className="flex items-center gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
                                        <Tooltip>
                                            <TooltipTrigger asChild>
                                                <Button
                                                    variant="ghost"
                                                    size="icon"
                                                    className="h-7 w-7"
                                                    onClick={(e) => {
                                                        e.stopPropagation()
                                                        duplicateStep(index)
                                                    }}
                                                >
                                                    <Copy className="h-3.5 w-3.5" />
                                                </Button>
                                            </TooltipTrigger>
                                            <TooltipContent>{t("macroEditor.duplicate")}</TooltipContent>
                                        </Tooltip>
                                        <Tooltip>
                                            <TooltipTrigger asChild>
                                                <Button
                                                    variant="ghost"
                                                    size="icon"
                                                    className="h-7 w-7 text-destructive hover:text-destructive"
                                                    onClick={(e) => {
                                                        e.stopPropagation()
                                                        deleteStep(index)
                                                    }}
                                                >
                                                    <Trash2 className="h-3.5 w-3.5" />
                                                </Button>
                                            </TooltipTrigger>
                                            <TooltipContent>{t("macroEditor.delete")}</TooltipContent>
                                        </Tooltip>
                                    </div>
                                )}
                            </div>

                            {/* Expanded step editor */}
                            {expandedSteps.has(index) && (
                                <div className="p-4 border-t bg-background">
                                    <div className="grid grid-cols-4 gap-3">
                                        {/* Step type */}
                                        <div className="space-y-2">
                                            <Label className="text-xs">{t("macroEditor.type")}</Label>
                                            <Select
                                                value={(() => {
                                                    const commonActions = ["click", "navigate", "back", "input", "key_press", "wait"];
                                                    if (step.type === "action" && commonActions.includes(step.event_type || "")) {
                                                        return step.event_type;
                                                    }
                                                    return step.type;
                                                })()}
                                                onValueChange={(value: any) => {
                                                    const commonActions = ["click", "navigate", "input", "key_press", "wait"];
                                                    if (commonActions.includes(value)) {
                                                        updateStep(index, { type: "action", event_type: value });
                                                    } else {
                                                        updateStep(index, { type: value });
                                                    }
                                                }}
                                                disabled={readOnly}
                                            >
                                                <SelectTrigger>
                                                    <SelectValue />
                                                </SelectTrigger>
                                                <SelectContent>
                                                    <SelectItem value="action">{t("macroEditor.stepTypes.action")}</SelectItem>
                                                    <div className="h-px bg-muted my-1" />
                                                    <SelectItem value="click">{t("macroEditor.eventTypes.click")}</SelectItem>
                                                    <SelectItem value="navigate">{t("macroEditor.eventTypes.navigate")}</SelectItem>
                                                    <SelectItem value="back">{t("macroEditor.eventTypes.back")}</SelectItem>
                                                    <SelectItem value="input">{t("macroEditor.eventTypes.input")}</SelectItem>
                                                    <SelectItem value="key_press">{t("macroEditor.eventTypes.key_press")}</SelectItem>
                                                    <SelectItem value="wait">{t("macroEditor.eventTypes.wait")}</SelectItem>
                                                    <div className="h-px bg-muted my-1" />
                                                    <SelectItem value="extract">{t("macroEditor.stepTypes.extract")}</SelectItem>
                                                    <SelectItem value="if">{t("macroEditor.stepTypes.if")}</SelectItem>
                                                    <SelectItem value="loop">{t("macroEditor.stepTypes.loop")}</SelectItem>
                                                    <SelectItem value="control">{t("macroEditor.stepTypes.control")}</SelectItem>
                                                    <SelectItem value="dump">{t("macroEditor.stepTypes.dump")}</SelectItem>
                                                </SelectContent>
                                            </Select>
                                        </div>

                                        {/* Source */}
                                        <div className="space-y-2">
                                            <Label className="text-xs">{t("macroEditor.source")}</Label>
                                            <Select
                                                value={step.source}
                                                onValueChange={(value: any) =>
                                                    updateStep(index, { source: value })
                                                }
                                                disabled={readOnly}
                                            >
                                                <SelectTrigger>
                                                    <SelectValue />
                                                </SelectTrigger>
                                                <SelectContent>
                                                    <SelectItem value="dom">{t("macroEditor.sources.dom")}</SelectItem>
                                                    <SelectItem value="mobile">{t("macroEditor.sources.mobile")}</SelectItem>
                                                    <SelectItem value="desktop">{t("macroEditor.sources.desktop")}</SelectItem>
                                                    <SelectItem value="hybrid">{t("macroEditor.sources.hybrid")}</SelectItem>
                                                </SelectContent>
                                            </Select>
                                        </div>

                                        {/* Event type - Only show for generic "action" that isn't virtualized */}
                                        {(() => {
                                            const commonActions = ["click", "navigate", "input", "key_press", "wait"];
                                            const isVirtualType = commonActions.includes(step.event_type || "");
                                            const isGenericAction = step.type === "action" && !isVirtualType;

                                            if (!isGenericAction) return null;

                                            return (
                                                <div className="space-y-2">
                                                    <Label className="text-xs">{t("macroEditor.eventType")}</Label>
                                                    <Select
                                                        value={step.event_type}
                                                        onValueChange={(value) =>
                                                            updateStep(index, { event_type: value })
                                                        }
                                                        disabled={readOnly}
                                                    >
                                                        <SelectTrigger>
                                                            <SelectValue />
                                                        </SelectTrigger>
                                                        <SelectContent>
                                                            {(eventTypes[step.source] || eventTypes.dom).map(
                                                                (event: any) => (
                                                                    <SelectItem key={event.value} value={event.value}>
                                                                        <div className="flex items-center gap-2">
                                                                            {event.icon}
                                                                            {t(`macroEditor.eventTypes.${event.value}`)}
                                                                        </div>
                                                                    </SelectItem>
                                                                )
                                                            )}
                                                        </SelectContent>
                                                    </Select>
                                                </div>
                                            );
                                        })()}

                                        {/* Selector type */}
                                        <div className="space-y-2">
                                            <Label className="text-xs">{t("macroEditor.selectorType")}</Label>
                                            <Select
                                                value={step.selector_type || "css"}
                                                onValueChange={(value: any) =>
                                                    updateStep(index, { selector_type: value })
                                                }
                                                disabled={readOnly}
                                            >
                                                <SelectTrigger>
                                                    <SelectValue />
                                                </SelectTrigger>
                                                <SelectContent>
                                                    <SelectItem value="css">{t("macroEditor.selectorTypes.css")}</SelectItem>
                                                    <SelectItem value="xpath">{t("macroEditor.selectorTypes.xpath")}</SelectItem>
                                                    <SelectItem value="text">{t("macroEditor.selectorTypes.text")}</SelectItem>
                                                    <SelectItem value="id">{t("macroEditor.selectorTypes.id")}</SelectItem>
                                                </SelectContent>
                                            </Select>
                                        </div>

                                        {/* Condition Configurator for If/Loop */}
                                        {(step.type === "if" || step.type === "loop") && (
                                            <div className="col-span-4 p-3 border rounded-md bg-muted/20 space-y-3">
                                                <div className="flex items-center gap-2 text-sm font-medium">
                                                    <Settings2 className="h-4 w-4" />
                                                    {t("macroEditor.conditionConfig")}
                                                </div>
                                                <div className="grid grid-cols-2 gap-3">
                                                    {(step.type === "if" || (step.type === "loop" && !step.payload?.items_key)) ? (
                                                        <>
                                                            <div className="space-y-2">
                                                                <Label className="text-xs">{t("macroEditor.conditionType")}</Label>
                                                                <Select
                                                                    value={step.condition?.type || "element_exists"}
                                                                    onValueChange={(value) =>
                                                                        updateStep(index, {
                                                                            condition: { type: value, target_selector: step.condition?.target_selector }
                                                                        })
                                                                    }
                                                                    disabled={readOnly}
                                                                >
                                                                    <SelectTrigger>
                                                                        <SelectValue />
                                                                    </SelectTrigger>
                                                                    <SelectContent>
                                                                        <SelectItem value="element_exists">{t("macroEditor.conditions.elementExists")}</SelectItem>
                                                                        <SelectItem value="element_visible">{t("macroEditor.conditions.elementVisible")}</SelectItem>
                                                                        <SelectItem value="text_contains">{t("macroEditor.conditions.textContains")}</SelectItem>
                                                                    </SelectContent>
                                                                </Select>
                                                            </div>
                                                            <div className="space-y-2">
                                                                <Label className="text-xs">{t("macroEditor.targetSelector")}</Label>
                                                                <Input
                                                                    value={step.condition?.target_selector || ""}
                                                                    onChange={(e) =>
                                                                        updateStep(index, {
                                                                            condition: {
                                                                                type: step.condition?.type || "element_exists",
                                                                                target_selector: e.target.value
                                                                            }
                                                                        })
                                                                    }
                                                                    placeholder={t("macroEditor.placeholders.selector")}
                                                                    disabled={readOnly}
                                                                />
                                                            </div>
                                                        </>
                                                    ) : (
                                                        <div className="space-y-2">
                                                            <Label className="text-xs">Items Key</Label>
                                                            <Input
                                                                value={step.payload?.items_key || ""}
                                                                onChange={(e) =>
                                                                    updateStep(index, {
                                                                        payload: { ...step.payload, items_key: e.target.value }
                                                                    })
                                                                }
                                                                placeholder="e.g. products"
                                                                disabled={readOnly}
                                                            />
                                                        </div>
                                                    )}
                                                    {step.type === "loop" && (
                                                        <div className="space-y-2">
                                                            <Label className="text-xs">{t("macroEditor.maxIterations")}</Label>
                                                            <Input
                                                                type="number"
                                                                value={step.max_iterations || 10}
                                                                onChange={(e) =>
                                                                    updateStep(index, {
                                                                        max_iterations: parseInt(e.target.value) || 10
                                                                    })
                                                                }
                                                                disabled={readOnly}
                                                            />
                                                        </div>
                                                    )}
                                                </div>
                                            </div>
                                        )}

                                        {/* Recursive Nested Steps for If (Then/Else) */}
                                        {step.type === "if" && (
                                            <div className="col-span-4 space-y-4 pt-2 border-t mt-2">
                                                <div className="space-y-2">
                                                    <Label className="text-sm font-semibold text-cyan-600 flex items-center gap-1">
                                                        <ChevronRight className="h-4 w-4" /> {t("macroEditor.thenBranch")}
                                                    </Label>
                                                    <div className="pl-4 border-l-2 border-cyan-500/30 ml-2">
                                                        <MacroEditor
                                                            steps={step.then_steps || []}
                                                            onChange={(newSteps) => updateStep(index, { then_steps: newSteps })}
                                                            readOnly={readOnly}
                                                            onStepPreview={onStepPreview}
                                                            videoPath={videoPath}
                                                        />
                                                    </div>
                                                </div>
                                                <div className="space-y-2">
                                                    <Label className="text-sm font-semibold text-amber-600 flex items-center gap-1">
                                                        <ChevronRight className="h-4 w-4" /> {t("macroEditor.elseBranch")}
                                                    </Label>
                                                    <div className="pl-4 border-l-2 border-amber-500/30 ml-2">
                                                        <MacroEditor
                                                            steps={step.else_steps || []}
                                                            onChange={(newSteps) => updateStep(index, { else_steps: newSteps })}
                                                            readOnly={readOnly}
                                                            onStepPreview={onStepPreview}
                                                            videoPath={videoPath}
                                                        />
                                                    </div>
                                                </div>
                                            </div>
                                        )}

                                        {/* Recursive Nested Steps for Loop (Steps) */}
                                        {step.type === "loop" && (
                                            <div className="col-span-4 space-y-4 pt-2 border-t mt-2">
                                                <div className="space-y-2">
                                                    <Label className={cn(
                                                        "text-sm font-semibold flex items-center gap-1",
                                                        !step.payload?.items_key ? "text-rose-600" : "text-orange-600"
                                                    )}>
                                                        <ChevronRight className="h-4 w-4" /> {t("macroEditor.loopSteps")}
                                                    </Label>
                                                    <div className={cn(
                                                        "pl-4 border-l-2 ml-2",
                                                        !step.payload?.items_key ? "border-rose-500/30" : "border-orange-500/30"
                                                    )}>
                                                        <MacroEditor
                                                            steps={step.steps || []}
                                                            onChange={(newSteps) => updateStep(index, { steps: newSteps })}
                                                            readOnly={readOnly}
                                                            onStepPreview={onStepPreview}
                                                            videoPath={videoPath}
                                                        />
                                                    </div>
                                                </div>
                                            </div>
                                        )}

                                        {/* Selector */}
                                        {step.type !== "if" && step.type !== "loop" && (
                                            <div className="col-span-4 space-y-2">
                                                <Label className="text-xs">{t("macroEditor.selector")}</Label>
                                                <div className="flex gap-2">
                                                    <Input
                                                        value={step.selector || ""}
                                                        onChange={(e) =>
                                                            updateStep(index, { selector: e.target.value })
                                                        }
                                                        placeholder={
                                                            step.selector_type === "css"
                                                                ? t("macroEditor.placeholders.cssSelector")
                                                                : step.selector_type === "xpath"
                                                                    ? t("macroEditor.placeholders.xpath")
                                                                    : t("macroEditor.placeholders.selector")
                                                        }
                                                        disabled={readOnly}
                                                        className="font-mono text-sm"
                                                    />
                                                    {videoPath && onStepPreview && (
                                                        <Tooltip>
                                                            <TooltipTrigger asChild>
                                                                <Button
                                                                    variant="outline"
                                                                    size="icon"
                                                                    onClick={() => onStepPreview(step)}
                                                                >
                                                                    <Play className="h-4 w-4" />
                                                                </Button>
                                                            </TooltipTrigger>
                                                            <TooltipContent>{t("macroEditor.previewStep")}</TooltipContent>
                                                        </Tooltip>
                                                    )}
                                                </div>
                                            </div>
                                        )}

                                        {/* Description */}
                                        <div className="col-span-4 space-y-2">
                                            <Label className="text-xs">{t("macroEditor.description")}</Label>
                                            <Input
                                                value={step.description || ""}
                                                onChange={(e) =>
                                                    updateStep(index, { description: e.target.value })
                                                }
                                                placeholder={t("macroEditor.placeholders.description")}
                                                disabled={readOnly}
                                            />
                                        </div>

                                        {/* Payload (collapsible) */}
                                        <div className="col-span-4 space-y-2">
                                            <Label className="text-xs">{t("macroEditor.payload")}</Label>
                                            <Textarea
                                                value={
                                                    step.payload
                                                        ? JSON.stringify(step.payload, null, 2)
                                                        : ""
                                                }
                                                onChange={(e) => {
                                                    try {
                                                        const payload = e.target.value
                                                            ? JSON.parse(e.target.value)
                                                            : undefined
                                                        updateStep(index, { payload })
                                                    } catch {
                                                        // Allow invalid JSON while typing
                                                    }
                                                }}
                                                placeholder={t("macroEditor.placeholders.payload")}
                                                disabled={readOnly}
                                                className="font-mono text-xs min-h-[80px]"
                                            />
                                        </div>

                                        {/* URL (for navigate) */}
                                        {step.event_type === "navigate" && (
                                            <div className="col-span-4 space-y-2">
                                                <Label className="text-xs">{t("macroEditor.url")}</Label>
                                                <Input
                                                    value={step.url || ""}
                                                    onChange={(e) =>
                                                        updateStep(index, { url: e.target.value })
                                                    }
                                                    placeholder={t("macroEditor.placeholders.url")}
                                                    disabled={readOnly}
                                                />
                                            </div>
                                        )}

                                        {/* Timeout */}
                                        <div className="space-y-2">
                                            <Label className="text-xs">{t("macroEditor.timeout")}</Label>
                                            <Input
                                                type="number"
                                                value={step.timeout_ms || ""}
                                                onChange={(e) =>
                                                    updateStep(index, {
                                                        timeout_ms: e.target.value
                                                            ? parseInt(e.target.value)
                                                            : undefined,
                                                    })
                                                }
                                                placeholder={t("macroEditor.placeholders.timeout")}
                                                disabled={readOnly}
                                            />
                                        </div>
                                    </div>

                                    {/* Add step after */}
                                    {!readOnly && (
                                        <div className="mt-4 pt-4 border-t">
                                            <Button
                                                variant="outline"
                                                size="sm"
                                                onClick={() => addStep(index)}
                                                className="w-full"
                                            >
                                                <Plus className="h-4 w-4 mr-2" />
                                                {t("macroEditor.addStepAfter")}
                                            </Button>
                                        </div>
                                    )}
                                </div>
                            )}
                        </div>
                    ))}

                    {steps.length === 0 && (
                        <div className="flex flex-col items-center justify-center py-12 text-muted-foreground">
                            <MousePointerClick className="h-12 w-12 mb-4 opacity-30" />
                            <p>{t("macroEditor.noMacroSteps")}</p>
                            {!readOnly && (
                                <Button
                                    variant="outline"
                                    size="sm"
                                    onClick={() => addStep()}
                                    className="mt-4"
                                >
                                    <Plus className="h-4 w-4 mr-2" />
                                    {t("macroEditor.addFirstStep")}
                                </Button>
                            )}
                        </div>
                    )}
                </div>
            </div>
        </TooltipProvider>
    )
}

// JSON Editor Dialog for advanced editing
export function MacroJsonEditor({
    steps,
    onChange,
    children,
}: {
    steps: MacroStep[]
    onChange: (steps: MacroStep[]) => void
    children: React.ReactNode
}) {
    const { t } = useTranslation()
    const [jsonValue, setJsonValue] = useState(JSON.stringify(steps, null, 2))
    const [error, setError] = useState<string | null>(null)
    const [open, setOpen] = useState(false)

    const handleSave = () => {
        try {
            const parsed = JSON.parse(jsonValue)
            if (!Array.isArray(parsed)) {
                setError(t("macroEditor.jsonErrorArray"))
                return
            }
            onChange(parsed)
            setError(null)
            setOpen(false)
        } catch (e) {
            setError(t("macroEditor.jsonErrorInvalid") + (e as Error).message)
        }
    }

    return (
        <Dialog open={open} onOpenChange={setOpen}>
            <DialogTrigger asChild>{children}</DialogTrigger>
            <DialogContent className="max-w-3xl max-h-[80vh]">
                <DialogHeader>
                    <DialogTitle>{t("macroEditor.editMacroJson")}</DialogTitle>
                </DialogHeader>
                <div className="space-y-4">
                    <Textarea
                        value={jsonValue}
                        onChange={(e) => setJsonValue(e.target.value)}
                        className="font-mono text-xs min-h-[400px]"
                    />
                    {error && (
                        <div className="text-sm text-destructive bg-destructive/10 p-2 rounded">
                            {error}
                        </div>
                    )}
                    <div className="flex justify-end gap-2">
                        <Button variant="outline" onClick={() => setOpen(false)}>
                            {t("macroEditor.cancel")}
                        </Button>
                        <Button onClick={handleSave}>{t("macroEditor.saveChanges")}</Button>
                    </div>
                </div>
            </DialogContent>
        </Dialog>
    )
}
