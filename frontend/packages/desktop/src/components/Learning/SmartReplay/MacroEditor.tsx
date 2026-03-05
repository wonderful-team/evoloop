/**
 * MacroEditor - Visual editor for macro scripts
 *
 * Features:
 * - Drag-and-drop step reordering
 * - Visual step editing with form fields
 * - Step preview with video sync
 * - Add/remove step functionality
 */

import { useState, useCallback } from "react"
import {
    GripVertical,
    Trash2,
    Plus,
    ChevronDown,
    ChevronRight,
    Play,
    Pause,
    Copy,
    Check,
    MousePointerClick,
    Keyboard,
    Eye,
    Clock,
    ArrowRight,
    Type,
    Download,
    Upload,
    Undo2,
    RefreshCw,
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
import { cn } from "@evoloop/shared/lib/utils"

// Macro step types
export interface MacroStep {
    step_number: number
    type: "action" | "extract" | "dump" | "wait"
    source: "dom" | "mobile" | "desktop" | "hybrid"
    event_type?: string
    selector?: string
    selector_type?: "css" | "xpath" | "text" | "id"
    payload?: Record<string, any>
    url?: string
    wait_condition?: string
    timeout_ms?: number
    description?: string
}

interface MacroEditorProps {
    steps: MacroStep[]
    videoPath?: string
    onChange: (steps: MacroStep[]) => void
    onStepPreview?: (step: MacroStep, timestampMs?: number) => void
    readOnly?: boolean
}

// Event type options grouped by source
const EVENT_TYPES: Record<string, { value: string; label: string; icon: React.ReactNode }[]> = {
    dom: [
        { value: "navigate", label: "Navigate", icon: <ArrowRight className="h-4 w-4" /> },
        { value: "click", label: "Click", icon: <MousePointerClick className="h-4 w-4" /> },
        { value: "input", label: "Input", icon: <Keyboard className="h-4 w-4" /> },
        { value: "scroll", label: "Scroll", icon: <RefreshCw className="h-4 w-4" /> },
        { value: "wait", label: "Wait", icon: <Clock className="h-4 w-4" /> },
        { value: "extract", label: "Extract Data", icon: <Download className="h-4 w-4" /> },
        { value: "screenshot", label: "Screenshot", icon: <Eye className="h-4 w-4" /> },
    ],
    mobile: [
        { value: "tap", label: "Tap", icon: <MousePointerClick className="h-4 w-4" /> },
        { value: "swipe", label: "Swipe", icon: <RefreshCw className="h-4 w-4" /> },
        { value: "input", label: "Input", icon: <Keyboard className="h-4 w-4" /> },
        { value: "dump_ui", label: "Dump UI", icon: <Eye className="h-4 w-4" /> },
        { value: "wait", label: "Wait", icon: <Clock className="h-4 w-4" /> },
    ],
    desktop: [
        { value: "applescript", label: "AppleScript", icon: <Type className="h-4 w-4" /> },
        { value: "keypress", label: "Key Press", icon: <Keyboard className="h-4 w-4" /> },
        { value: "click", label: "Click", icon: <MousePointerClick className="h-4 w-4" /> },
        { value: "wait", label: "Wait", icon: <Clock className="h-4 w-4" /> },
    ],
}

export function MacroEditor({
    steps,
    videoPath,
    onChange,
    onStepPreview,
    readOnly = false,
}: MacroEditorProps) {
    const [expandedSteps, setExpandedSteps] = useState<Set<number>>(new Set([0]))
    const [editingStep, setEditingStep] = useState<number | null>(null)
    const [draggingIndex, setDraggingIndex] = useState<number | null>(null)
    const [copiedStep, setCopiedStep] = useState<MacroStep | null>(null)
    const [originalSteps] = useState<MacroStep[]>(JSON.parse(JSON.stringify(steps)))

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
            description: "New step",
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
        const sourceEvents = EVENT_TYPES[step.source] || EVENT_TYPES.dom
        const eventType = sourceEvents.find((e) => e.value === step.event_type)
        return eventType?.icon || <MousePointerClick className="h-4 w-4" />
    }, [])

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
                                {steps.length} steps
                            </span>
                            <div className="w-px h-4 bg-border mx-2" />
                            <Badge variant="outline" className="text-xs">
                                {steps.filter((s) => s.type === "action").length} actions
                            </Badge>
                            <Badge variant="outline" className="text-xs bg-blue-500/10">
                                {steps.filter((s) => s.type === "extract").length} extracts
                            </Badge>
                            <Badge variant="outline" className="text-xs bg-amber-500/10">
                                {steps.filter((s) => s.type === "wait").length} waits
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
                                        Reset
                                    </Button>
                                </TooltipTrigger>
                                <TooltipContent>Reset to original</TooltipContent>
                            </Tooltip>
                            <Tooltip>
                                <TooltipTrigger asChild>
                                    <Button
                                        variant="ghost"
                                        size="sm"
                                        onClick={() => addStep()}
                                    >
                                        <Plus className="h-4 w-4 mr-1" />
                                        Add Step
                                    </Button>
                                </TooltipTrigger>
                                <TooltipContent>Add new step at the end</TooltipContent>
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
                                    "flex items-center gap-2 p-3 cursor-pointer hover:bg-muted/50 transition-colors",
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
                                    {step.event_type || step.type}
                                </Badge>

                                <span className="flex-1 truncate text-sm">
                                    {step.description || step.selector || "No description"}
                                </span>

                                <Badge variant="outline" className="text-xs">
                                    {step.source}
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
                                            <TooltipContent>Duplicate</TooltipContent>
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
                                            <TooltipContent>Delete</TooltipContent>
                                        </Tooltip>
                                    </div>
                                )}
                            </div>

                            {/* Expanded step editor */}
                            {expandedSteps.has(index) && (
                                <div className="p-4 border-t bg-background">
                                    <div className="grid grid-cols-2 gap-4">
                                        {/* Step type */}
                                        <div className="space-y-2">
                                            <Label className="text-xs">Type</Label>
                                            <Select
                                                value={step.type}
                                                onValueChange={(value: any) =>
                                                    updateStep(index, { type: value })
                                                }
                                                disabled={readOnly}
                                            >
                                                <SelectTrigger>
                                                    <SelectValue />
                                                </SelectTrigger>
                                                <SelectContent>
                                                    <SelectItem value="action">Action</SelectItem>
                                                    <SelectItem value="extract">Extract</SelectItem>
                                                    <SelectItem value="wait">Wait</SelectItem>
                                                    <SelectItem value="dump">Dump UI</SelectItem>
                                                </SelectContent>
                                            </Select>
                                        </div>

                                        {/* Source */}
                                        <div className="space-y-2">
                                            <Label className="text-xs">Source</Label>
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
                                                    <SelectItem value="dom">Web (DOM)</SelectItem>
                                                    <SelectItem value="mobile">Mobile</SelectItem>
                                                    <SelectItem value="desktop">Desktop</SelectItem>
                                                    <SelectItem value="hybrid">Hybrid</SelectItem>
                                                </SelectContent>
                                            </Select>
                                        </div>

                                        {/* Event type */}
                                        <div className="space-y-2">
                                            <Label className="text-xs">Event Type</Label>
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
                                                    {(EVENT_TYPES[step.source] || EVENT_TYPES.dom).map(
                                                        (event) => (
                                                            <SelectItem key={event.value} value={event.value}>
                                                                <div className="flex items-center gap-2">
                                                                    {event.icon}
                                                                    {event.label}
                                                                </div>
                                                            </SelectItem>
                                                        )
                                                    )}
                                                </SelectContent>
                                            </Select>
                                        </div>

                                        {/* Selector type */}
                                        <div className="space-y-2">
                                            <Label className="text-xs">Selector Type</Label>
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
                                                    <SelectItem value="css">CSS Selector</SelectItem>
                                                    <SelectItem value="xpath">XPath</SelectItem>
                                                    <SelectItem value="text">Text Content</SelectItem>
                                                    <SelectItem value="id">ID</SelectItem>
                                                </SelectContent>
                                            </Select>
                                        </div>

                                        {/* Selector */}
                                        <div className="col-span-2 space-y-2">
                                            <Label className="text-xs">Selector</Label>
                                            <div className="flex gap-2">
                                                <Input
                                                    value={step.selector || ""}
                                                    onChange={(e) =>
                                                        updateStep(index, { selector: e.target.value })
                                                    }
                                                    placeholder={
                                                        step.selector_type === "css"
                                                            ? "e.g., .product-price or #submit-btn"
                                                            : step.selector_type === "xpath"
                                                                ? "e.g., //button[contains(text(), 'Submit')]"
                                                                : "Enter selector..."
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
                                                        <TooltipContent>Preview this step</TooltipContent>
                                                    </Tooltip>
                                                )}
                                            </div>
                                        </div>

                                        {/* Description */}
                                        <div className="col-span-2 space-y-2">
                                            <Label className="text-xs">Description</Label>
                                            <Input
                                                value={step.description || ""}
                                                onChange={(e) =>
                                                    updateStep(index, { description: e.target.value })
                                                }
                                                placeholder="Describe what this step does..."
                                                disabled={readOnly}
                                            />
                                        </div>

                                        {/* Payload (collapsible) */}
                                        <div className="col-span-2 space-y-2">
                                            <Label className="text-xs">Payload (JSON)</Label>
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
                                                placeholder='{"key": "value"}'
                                                disabled={readOnly}
                                                className="font-mono text-xs min-h-[80px]"
                                            />
                                        </div>

                                        {/* URL (for navigate) */}
                                        {step.event_type === "navigate" && (
                                            <div className="col-span-2 space-y-2">
                                                <Label className="text-xs">URL</Label>
                                                <Input
                                                    value={step.url || ""}
                                                    onChange={(e) =>
                                                        updateStep(index, { url: e.target.value })
                                                    }
                                                    placeholder="https://example.com"
                                                    disabled={readOnly}
                                                />
                                            </div>
                                        )}

                                        {/* Timeout */}
                                        <div className="space-y-2">
                                            <Label className="text-xs">Timeout (ms)</Label>
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
                                                placeholder="5000"
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
                                                Add Step After
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
                            <p>No macro steps yet</p>
                            {!readOnly && (
                                <Button
                                    variant="outline"
                                    size="sm"
                                    onClick={() => addStep()}
                                    className="mt-4"
                                >
                                    <Plus className="h-4 w-4 mr-2" />
                                    Add First Step
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
    const [jsonValue, setJsonValue] = useState(JSON.stringify(steps, null, 2))
    const [error, setError] = useState<string | null>(null)
    const [open, setOpen] = useState(false)

    const handleSave = () => {
        try {
            const parsed = JSON.parse(jsonValue)
            if (!Array.isArray(parsed)) {
                setError("Must be an array of steps")
                return
            }
            onChange(parsed)
            setError(null)
            setOpen(false)
        } catch (e) {
            setError("Invalid JSON: " + (e as Error).message)
        }
    }

    return (
        <Dialog open={open} onOpenChange={setOpen}>
            <DialogTrigger asChild>{children}</DialogTrigger>
            <DialogContent className="max-w-3xl max-h-[80vh]">
                <DialogHeader>
                    <DialogTitle>Edit Macro JSON</DialogTitle>
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
                            Cancel
                        </Button>
                        <Button onClick={handleSave}>Save Changes</Button>
                    </div>
                </div>
            </DialogContent>
        </Dialog>
    )
}
