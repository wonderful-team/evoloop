import React from "react";
import { useTranslation } from "react-i18next";
import {
    Repeat,
    GitBranch,
    FolderTree,
    ChevronDown,
    Trash2,
    ChevronUp
} from "lucide-react";
import { Button } from "@evoloop/shared/components/ui/button";
import { Input } from "@evoloop/shared/components/ui/input";
import { Label } from "@evoloop/shared/components/ui/label";
import { SkillStep } from "@/types/skill";

interface LogicHeaderProps {
    step: SkillStep;
    index: number;
    totalSteps: number;
    onUpdate: (step: SkillStep) => void;
    onDelete: () => void;
    onMove: (direction: 'up' | 'down') => void;
}

export const LogicHeader: React.FC<LogicHeaderProps> = ({
    step,
    index,
    totalSteps,
    onUpdate,
    onDelete,
    onMove,
}) => {
    const { t } = useTranslation();

    const getIcon = () => {
        switch (step.action) {
            case "loop": return <Repeat className="w-4 h-4 text-amber-500" />;
            case "condition": return <GitBranch className="w-4 h-4 text-blue-500" />;
            case "group": return <FolderTree className="w-4 h-4 text-emerald-500" />;
            default: return null;
        }
    };

    const getLabel = () => {
        switch (step.action) {
            case "loop": return t("skills.actions.loop", "Loop");
            case "condition": return t("skills.actions.condition", "Condition");
            case "group": return t("skills.actions.group", "Group");
            default: return step.action;
        }
    };

    const renderArgs = () => {
        if (step.action === "loop") {
            return (
                <div className="flex items-center gap-2">
                    <Label className="text-[10px] text-muted-foreground uppercase font-bold">{t("skills.actions.loopCount", "Count")}:</Label>
                    <Input
                        type="number"
                        value={step.args.count || 0}
                        onChange={(e) => onUpdate({ ...step, args: { ...step.args, count: parseInt(e.target.value) } })}
                        className="h-7 w-16 text-xs font-mono bg-muted/20 border-none"
                    />
                </div>
            );
        }
        if (step.action === "condition") {
            return (
                <div className="flex items-center gap-2 flex-1 max-w-sm">
                    <Label className="text-[10px] text-muted-foreground uppercase font-bold">{t("skills.actions.if", "If")}:</Label>
                    <Input
                        value={step.args.if || ""}
                        onChange={(e) => onUpdate({ ...step, args: { ...step.args, if: e.target.value } })}
                        className="h-7 flex-1 text-xs font-mono bg-muted/20 border-none"
                        placeholder={t("learning.headers.conditionPlaceholder", "e.g. 1 == 1")}
                    />
                </div>
            );
        }
        return null;
    };

    return (
        <div className="flex items-center justify-between p-3 bg-muted/5 rounded-t-xl border-b transition-colors group-hover:bg-muted/10">
            <div className="flex items-center gap-4 flex-1">
                <div className="flex items-center gap-2">
                    <div className="p-1 px-2 rounded-lg bg-background border shadow-sm flex items-center gap-2">
                        {getIcon()}
                        <span className="text-xs font-bold tracking-tight">{getLabel()}</span>
                    </div>
                </div>
                {renderArgs()}
            </div>

            <div className="flex items-center gap-1">
                <Button
                    variant="ghost"
                    size="icon"
                    className="h-7 w-7 text-muted-foreground hover:text-primary rounded-lg disabled:opacity-20"
                    onClick={() => onMove('up')}
                    disabled={index === 0}
                >
                    <ChevronUp className="h-4 w-4" />
                </Button>
                <Button
                    variant="ghost"
                    size="icon"
                    className="h-7 w-7 text-muted-foreground hover:text-primary rounded-lg disabled:opacity-20"
                    onClick={() => onMove('down')}
                    disabled={index === totalSteps - 1}
                >
                    <ChevronDown className="h-4 w-4" />
                </Button>
                <div className="w-px h-3 bg-muted mx-1" />
                <Button
                    variant="ghost"
                    size="icon"
                    className="h-7 w-7 text-muted-foreground hover:text-destructive rounded-lg"
                    onClick={() => onDelete()}
                >
                    <Trash2 className="h-3.5 w-3.5" />
                </Button>
            </div>
        </div>
    );
};
