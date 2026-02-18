import React, { useState, useRef } from "react";
import { toast } from "sonner";
import { OpenAPI } from "@/client/core/OpenAPI";
import { SkillStep } from "@/types/skill";
import { Card } from "@evoloop/shared/components/ui/card";
import { Input } from "@evoloop/shared/components/ui/input";
import { Label } from "@evoloop/shared/components/ui/label";
import { Button } from "@evoloop/shared/components/ui/button";
import {
    Smartphone,
    Monitor,
    Camera,
    Hourglass,
    Plus,
    Trash2,
    ChevronUp,
    ChevronDown,
    Play,
    Braces,
    MousePointer2,
    Repeat,
    GitBranch,
    FolderTree
} from "lucide-react";
import {
    DropdownMenu,
    DropdownMenuContent,
    DropdownMenuItem,
    DropdownMenuTrigger,
} from "@evoloop/shared/components/ui/dropdown-menu";
import { useTranslation } from "react-i18next";
import { StepActionSelector } from "./StepActionSelector";
import { LogicHeader } from "./LogicHeader";
import { LogicContainer } from "./LogicContainer";

interface SimpleStepCardProps {
    step: SkillStep;
    index: number;
    path: number[];
    totalSteps: number;
    availableParams?: any[];
    onUpdate: (newStep: SkillStep) => void;
    onDelete: () => void;
    onMove: (direction: 'up' | 'down') => void;
    onInsert: () => void;
    onAddInner?: () => void;
    isActive?: boolean;
    children?: React.ReactNode;
}

export const SimpleStepCard: React.FC<SimpleStepCardProps> = ({
    step,
    index,
    totalSteps,
    availableParams = [],
    onUpdate,
    onDelete,
    onMove,
    onInsert,
    onAddInner,
    isActive,
    children,
}) => {
    const { t } = useTranslation();
    const [actionSelectorOpen, setActionSelectorOpen] = useState(false);
    const isLogic = ["loop", "condition", "group"].includes(step.action);

    // Helper to get icon based on action
    const getIcon = () => {
        if (step.action.includes("mobile")) return <Smartphone className="w-5 h-5" />;
        if (step.action.includes("desktop")) return <Monitor className="w-5 h-5" />;
        if (step.action === "wait") return <Hourglass className="w-5 h-5" />;
        if (step.action === "loop") return <Repeat className="w-5 h-5 text-amber-500" />;
        if (step.action === "condition") return <GitBranch className="w-5 h-5 text-blue-500" />;
        if (step.action === "group") return <FolderTree className="w-5 h-5 text-emerald-500" />;
        return <Play className="w-5 h-5" />;
    };

    // Helper to get friendly action name
    const getActionName = () => {
        const actionKey = step.action;
        if (step.action === "mobile_control") {
            const type = step.args.action || "unknown";
            return t(`skills.actions.mobile.${type}`, type) as string;
        }
        if (step.action === "desktop_control") {
            const type = step.args.action || "unknown";
            return t(`skills.actions.desktop.${type}`, type) as string;
        }
        if (step.action === "loop") return t("skills.actions.loop", "Loop");
        if (step.action === "condition") return t("skills.actions.condition", "Condition");
        if (step.action === "group") return t("skills.actions.group", "Group");

        return t(`skills.actions.${actionKey}`, actionKey) as string;
    };

    const handleActionChange = (newStep: SkillStep) => {
        onUpdate(newStep);
    };

    const fileInputRef = useRef<HTMLInputElement>(null);

    const handleScreenshotClick = () => {
        fileInputRef.current?.click();
    };

    const handleFileChange = async (event: React.ChangeEvent<HTMLInputElement>) => {
        const file = event.target.files?.[0];
        if (!file) return;

        const formData = new FormData();
        formData.append("file", file);

        try {
            const response = await fetch(`${OpenAPI.BASE}/learning/assets/upload-screenshot`, {
                method: "POST",
                body: formData,
            });

            if (!response.ok) throw new Error("Upload failed");

            const data = await response.json();
            if (data.success) {
                const newContext = {
                    ...step.visual_context,
                    screenshot_path: data.path,
                };
                onUpdate({ ...step, visual_context: newContext });
                toast.success(t("skills.editor.uploadSuccess", "Screenshot updated"));
            } else {
                throw new Error(data.message || "Upload failed");
            }
        } catch (error) {
            console.error("Failed to upload screenshot:", error);
            toast.error(t("skills.editor.uploadError", "Failed to update screenshot"));
        } finally {
            if (fileInputRef.current) fileInputRef.current.value = "";
        }
    };

    const insertVariable = (currentValue: string, variableName: string) => {
        return (currentValue || "") + `{{${variableName}}}`;
    };

    const renderArgs = () => {
        if (
            (step.action === "mobile_control" && (step.args.action === "tap" || step.args.action === "swipe")) ||
            (step.action === "desktop_control" && step.args.action === "click")
        ) {
            const isSwipe = step.args.action === "swipe";
            return (
                <div className="space-y-3">
                    <div className="flex items-center gap-4">
                        <div className="flex-1 space-y-1.5">
                            <Label className="text-[10px] uppercase font-bold text-muted-foreground">X {isSwipe && "Start"}</Label>
                            <div className="relative">
                                <MousePointer2 className="absolute left-2 top-1.5 h-3.5 w-3.5 text-muted-foreground/50" />
                                <Input
                                    className="h-8 pl-7 text-xs font-mono"
                                    type="number"
                                    value={step.args.x || step.args.x1 || 0}
                                    onChange={(e) => {
                                        const val = parseInt(e.target.value);
                                        const newArgs = isSwipe ? { ...step.args, x1: val } : { ...step.args, x: val };
                                        onUpdate({ ...step, args: newArgs });
                                    }}
                                />
                            </div>
                        </div>
                        <div className="flex-1 space-y-1.5">
                            <Label className="text-[10px] uppercase font-bold text-muted-foreground">Y {isSwipe && "Start"}</Label>
                            <div className="relative">
                                <MousePointer2 className="absolute left-2 top-1.5 h-3.5 w-3.5 text-muted-foreground/50" />
                                <Input
                                    className="h-8 pl-7 text-xs font-mono"
                                    type="number"
                                    value={step.args.y || step.args.y1 || 0}
                                    onChange={(e) => {
                                        const val = parseInt(e.target.value);
                                        const newArgs = isSwipe ? { ...step.args, y1: val } : { ...step.args, y: val };
                                        onUpdate({ ...step, args: newArgs });
                                    }}
                                />
                            </div>
                        </div>
                    </div>

                    {isSwipe && (
                        <div className="flex items-center gap-4 border-t border-dashed pt-3">
                            <div className="flex-1 space-y-1.5">
                                <Label className="text-[10px] uppercase font-bold text-muted-foreground">X End</Label>
                                <Input
                                    className="h-8 text-xs font-mono"
                                    type="number"
                                    value={step.args.x2 || 0}
                                    onChange={(e) => {
                                        onUpdate({ ...step, args: { ...step.args, x2: parseInt(e.target.value) } });
                                    }}
                                />
                            </div>
                            <div className="flex-1 space-y-1.5">
                                <Label className="text-[10px] uppercase font-bold text-muted-foreground">Y End</Label>
                                <Input
                                    className="h-8 text-xs font-mono"
                                    type="number"
                                    value={step.args.y2 || 0}
                                    onChange={(e) => {
                                        onUpdate({ ...step, args: { ...step.args, y2: parseInt(e.target.value) } });
                                    }}
                                />
                            </div>
                            <div className="flex-1 space-y-1.5">
                                <Label className="text-[10px] uppercase font-bold text-muted-foreground">Duration (ms)</Label>
                                <Input
                                    className="h-8 text-xs font-mono"
                                    type="number"
                                    value={step.args.duration || 500}
                                    onChange={(e) => {
                                        onUpdate({ ...step, args: { ...step.args, duration: parseInt(e.target.value) } });
                                    }}
                                />
                            </div>
                        </div>
                    )}
                </div>
            );
        }

        if (
            (step.action === "mobile_control" && step.args.action === "input_text") ||
            (step.action === "desktop_control" && step.args.action === "type_text")
        ) {
            return (
                <div className="space-y-1.5">
                    <div className="flex items-center justify-between">
                        <Label className="text-[10px] uppercase font-bold text-muted-foreground">{t('skills.editor.inputText', 'Input Text')}</Label>
                        {availableParams.length > 0 && (
                            <DropdownMenu>
                                <DropdownMenuTrigger asChild>
                                    <Button variant="ghost" size="sm" className="h-5 gap-1 text-[10px] px-2 text-primary hover:text-primary hover:bg-primary/5 -mr-2">
                                        <Braces className="h-3 w-3" />
                                        {t('learning.editor.insertVariable')}
                                    </Button>
                                </DropdownMenuTrigger>
                                <DropdownMenuContent align="end" className="w-48">
                                    {availableParams.map((p) => (
                                        <DropdownMenuItem
                                            key={p.name}
                                            className="text-xs cursor-pointer"
                                            onClick={() => {
                                                const newText = insertVariable(step.args.text, p.name);
                                                const newArgs = { ...step.args, text: newText };
                                                onUpdate({ ...step, args: newArgs });
                                            }}
                                        >
                                            <div className="flex flex-col gap-0.5">
                                                <span className="font-mono">{p.name}</span>
                                                <span className="text-[10px] text-muted-foreground line-clamp-1">{p.description}</span>
                                            </div>
                                        </DropdownMenuItem>
                                    ))}
                                </DropdownMenuContent>
                            </DropdownMenu>
                        )}
                    </div>
                    <Input
                        value={step.args.text || ""}
                        onChange={(e) => {
                            const newArgs = { ...step.args, text: e.target.value };
                            onUpdate({ ...step, args: newArgs });
                        }}
                        className="h-9 text-sm"
                        placeholder="Type something..."
                    />
                </div>
            )
        }

        if (step.action === "wait") {
            return (
                <div className="space-y-1.5">
                    <Label className="text-[10px] uppercase font-bold text-muted-foreground">{t('skills.actions.waitDesc', 'Duration (ms)')}</Label>
                    <div className="relative">
                        <Hourglass className="absolute left-2 top-1.5 h-3.5 w-3.5 text-muted-foreground/50" />
                        <Input
                            type="number"
                            value={step.args.duration || 1000}
                            onChange={(e) => {
                                const newArgs = { ...step.args, duration: parseInt(e.target.value) };
                                onUpdate({ ...step, args: newArgs });
                            }}
                            className="h-8 pl-7 text-xs font-mono"
                        />
                    </div>
                </div>
            )
        }

        return (
            <div className="grid gap-2">
                {Object.entries(step.args).map(([key, value]) => {
                    if (key === "action") return null;
                    if (typeof value === "object") return null;
                    return (
                        <div key={key} className="grid grid-cols-[80px_1fr] gap-2 items-center">
                            <Label className="text-xs truncate" title={key}>{key}</Label>
                            <Input
                                value={String(value)}
                                onChange={(e) => {
                                    const newArgs = { ...step.args, [key]: e.target.value };
                                    onUpdate({ ...step, args: newArgs });
                                }}
                                className="h-7 text-xs"
                            />
                        </div>
                    );
                })}
            </div>
        );
    };

    const snapshotUrl = step.visual_context?.screenshot_path
        ? `http://localhost:8000/static/${step.visual_context.screenshot_path.split('/').pop()}`
        : null;

    if (isLogic) {
        return (
            <div className={`relative pb-8 last:pb-0 transition-all duration-500 ${isActive ? "scale-[1.02] z-30" : ""}`}>
                <Card className={`relative overflow-hidden border bg-background shadow-sm hover:shadow-md transition-all group z-10 rounded-2xl ${isActive ? "border-emerald-500 ring-2 ring-emerald-500/20 shadow-emerald-500/10" : "hover:border-primary/40"}`}>
                    <LogicHeader
                        step={step}
                        index={index}
                        totalSteps={totalSteps}
                        onUpdate={onUpdate}
                        onDelete={onDelete}
                        onMove={onMove}
                    />
                    <div className="p-4">
                        <LogicContainer onAdd={onAddInner || (() => { })}>
                            {children}
                        </LogicContainer>
                    </div>
                </Card>

                {/* In-between Add Step Trigger */}
                <div className="absolute left-[40px] bottom-[-16px] z-20 group/add opacity-0 hover:opacity-100 transition-all focus-within:opacity-100">
                    <Button
                        variant="outline"
                        size="icon"
                        className="h-8 w-8 rounded-full border-primary/30 bg-background shadow-lg hover:bg-primary hover:text-white hover:border-primary transition-all scale-75 group-hover/add:scale-100"
                        onClick={onInsert}
                    >
                        <Plus className="h-4 w-4" />
                    </Button>
                </div>
            </div>
        );
    }

    return (
        <div className={`relative pb-8 last:pb-0 transition-all duration-500 ${isActive ? "scale-[1.02] z-30" : ""}`}>
            {index < totalSteps - 1 && (
                <div className="absolute left-[54px] top-24 bottom-0 w-0.5 bg-gradient-to-b from-primary/20 via-primary/10 to-transparent border-l border-dashed border-primary/20 z-0" />
            )}

            <Card className={`relative overflow-hidden border bg-background shadow-sm hover:shadow-md transition-all group z-10 rounded-2xl ${isActive ? "border-emerald-500 ring-2 ring-emerald-500/20 shadow-emerald-500/10" : "hover:border-primary/40"}`}>
                <div className="flex p-4 gap-5">
                    <input type="file" ref={fileInputRef} className="hidden" accept="image/*" onChange={handleFileChange} />
                    <div
                        className="w-24 h-24 bg-muted/30 rounded-xl flex-shrink-0 border border-muted/50 flex items-center justify-center overflow-hidden relative shadow-inner group-hover:border-primary/20 transition-colors cursor-pointer hover:opacity-80"
                        onClick={handleScreenshotClick}
                        title={t("skills.editor.changeScreenshot", "Click to change screenshot")}
                    >
                        {snapshotUrl ? (
                            <img src={snapshotUrl} alt="Step Context" className="w-full h-full object-cover transition-transform duration-500 group-hover:scale-110" />
                        ) : (
                            <div className="text-muted-foreground/30 flex flex-col items-center gap-1">
                                <Camera className="w-6 h-6" />
                                <span className="text-[10px] uppercase font-bold tracking-wider opacity-50">{t("skills.editor.noImage")}</span>
                            </div>
                        )}
                        <div className="absolute top-1.5 left-1.5 bg-background/90 backdrop-blur-sm text-[10px] font-black w-6 h-6 flex items-center justify-center rounded-lg border shadow-sm text-primary ring-1 ring-primary/5">
                            {index + 1}
                        </div>
                    </div>

                    <div className="flex-1 min-w-0 flex flex-col justify-between py-0.5">
                        <div className="space-y-3">
                            <div className="flex items-center justify-between">
                                <div
                                    className="flex items-center gap-2 cursor-pointer hover:bg-muted/50 p-1 rounded-lg -ml-1 transition-colors group/header"
                                    onClick={() => setActionSelectorOpen(true)}
                                >
                                    <div className="p-1.5 bg-primary/5 rounded-lg border border-primary/10 text-primary group-hover/header:bg-primary/10 transition-colors">
                                        {getIcon()}
                                    </div>
                                    <div className="flex items-center gap-1">
                                        <span className="font-bold text-sm tracking-tight">{getActionName()}</span>
                                        <ChevronDown className="h-3 w-3 text-muted-foreground opacity-30 group-hover/header:opacity-100 transition-opacity" />
                                    </div>
                                </div>

                                <div className="flex items-center gap-1 opacity-0 group-hover:opacity-100 transition-all translate-x-2 group-hover:translate-x-0">
                                    <Button
                                        variant="ghost"
                                        size="icon"
                                        className="h-8 w-8 text-muted-foreground hover:text-primary hover:bg-primary/5 rounded-lg disabled:opacity-30"
                                        onClick={() => onMove('up')}
                                        disabled={index === 0}
                                    >
                                        <ChevronUp className="h-4 w-4" />
                                    </Button>
                                    <Button
                                        variant="ghost"
                                        size="icon"
                                        className="h-8 w-8 text-muted-foreground hover:text-primary hover:bg-primary/5 rounded-lg disabled:opacity-30"
                                        onClick={() => onMove('down')}
                                        disabled={index === totalSteps - 1}
                                    >
                                        <ChevronDown className="h-4 w-4" />
                                    </Button>
                                    <div className="w-px h-4 bg-muted mx-1" />
                                    <Button
                                        variant="ghost"
                                        size="icon"
                                        className="h-8 w-8 text-muted-foreground hover:text-destructive hover:bg-destructive/5 rounded-lg"
                                        onClick={onDelete}
                                    >
                                        <Trash2 className="h-4 w-4" />
                                    </Button>
                                </div>
                            </div>
                        </div>

                        <div className="mt-3 bg-muted/10 p-3 rounded-xl border border-muted/20">
                            {renderArgs()}
                        </div>
                    </div>
                </div>
            </Card>

            <div className="absolute left-[40px] bottom-[-16px] z-20 group/add opacity-0 hover:opacity-100 transition-all focus-within:opacity-100">
                <Button
                    variant="outline"
                    size="icon"
                    className="h-8 w-8 rounded-full border-primary/30 bg-background shadow-lg hover:bg-primary hover:text-white hover:border-primary transition-all scale-75 group-hover/add:scale-100"
                    onClick={onInsert}
                >
                    <Plus className="h-4 w-4" />
                </Button>
            </div>

            <StepActionSelector open={actionSelectorOpen} onOpenChange={setActionSelectorOpen} onSelect={handleActionChange} />
        </div>
    );
};
