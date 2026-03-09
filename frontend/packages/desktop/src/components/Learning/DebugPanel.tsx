import React from "react";
import { useTranslation } from "react-i18next";
import {
    Bug,
    ChevronRight,
    Database,
    Terminal,
    X,
    Hash,
    Type,
    CircleDot
} from "lucide-react";
import { Card } from "@evoloop/shared/components/ui/card";
import { Button } from "@evoloop/shared/components/ui/button";
import { ScrollArea } from "@evoloop/shared/components/ui/scroll-area";
import { Badge } from "@evoloop/shared/components/ui/badge";
import { useChatStore } from "@/stores/chatStore";

interface DebugPanelProps {
    onClose: () => void;
}

export const DebugPanel: React.FC<DebugPanelProps> = ({ onClose }) => {
    const { t } = useTranslation();
    const { agentState, status } = useChatStore();

    const currentPath = agentState?.details?.step_path || [];
    const variables = agentState?.details?.variables || {};
    const previousResult = agentState?.details?.previous_result;

    const renderValue = (val: any) => {
        if (val === null) return <span className="text-muted-foreground italic">null</span>;
        if (val === undefined) return <span className="text-muted-foreground italic">undefined</span>;
        if (typeof val === "object") return <pre className="text-[10px] bg-muted/30 p-2 rounded-lg mt-1 overflow-x-auto">{JSON.stringify(val, null, 2)}</pre>;
        return <span className="font-mono text-primary">{String(val)}</span>;
    };

    const getVarIcon = (val: any) => {
        if (typeof val === "number") return <Hash className="w-3 h-3 text-amber-500" />;
        if (typeof val === "string") return <Type className="w-3 h-3 text-blue-500" />;
        return <CircleDot className="w-3 h-3 text-emerald-500" />;
    };

    return (
        <Card className="w-80 border-l bg-background/95 backdrop-blur-sm flex flex-col shadow-2xl h-full rounded-none">
            <div className="p-4 border-b flex items-center justify-between bg-muted/10">
                <div className="flex items-center gap-2">
                    <div className="p-1.5 bg-amber-500/10 rounded-lg text-amber-500">
                        <Bug className="w-4 h-4" />
                    </div>
                    <div>
                        <h3 className="text-xs font-bold uppercase tracking-wider">{t("learning.editor.debugPanel")}</h3>
                        <p className="text-[10px] text-muted-foreground">{status === "running" ? t("common.status.running") : t("common.status.idle")}</p>
                    </div>
                </div>
                <Button variant="ghost" size="icon" className="h-8 w-8 rounded-lg" onClick={onClose}>
                    <X className="w-4 h-4" />
                </Button>
            </div>

            <ScrollArea className="flex-1">
                <div className="p-4 space-y-6">
                    {/* Execution Path */}
                    <div className="space-y-3">
                        <div className="flex items-center gap-2 text-[10px] font-bold uppercase text-muted-foreground tracking-widest">
                            <ChevronRight className="w-3 h-3" />
                            {t("learning.editor.currentPath")}
                        </div>
                        {currentPath.length > 0 ? (
                            <div className="flex flex-wrap gap-1.5">
                                {currentPath.map((p: number, i: number) => (
                                    <React.Fragment key={i}>
                                        <Badge variant="outline" className="font-mono text-[10px] bg-primary/5 border-primary/20 text-primary">
                                            {p}
                                        </Badge>
                                        {i < currentPath.length - 1 && <span className="text-muted-foreground/30 px-0.5">/</span>}
                                    </React.Fragment>
                                ))}
                            </div>
                        ) : (
                            <div className="text-[10px] text-muted-foreground italic bg-muted/20 p-2 rounded-lg border border-dashed text-center">
                                {t("learning.editor.noActiveStep")}
                            </div>
                        )}
                    </div>

                    {/* Previous Result */}
                    <div className="space-y-3">
                        <div className="flex items-center gap-2 text-[10px] font-bold uppercase text-muted-foreground tracking-widest">
                            <Terminal className="w-3 h-3" />
                            {t("learning.editor.previousResult")}
                        </div>
                        <div className="bg-muted/30 p-3 rounded-xl border border-muted/50 max-h-40 overflow-hidden relative">
                            <div className="text-[11px] leading-relaxed break-all">
                                {previousResult ? renderValue(previousResult) : <span className="text-muted-foreground italic">{t("common.none")}</span>}
                            </div>
                        </div>
                    </div>

                    {/* Variables */}
                    <div className="space-y-3">
                        <div className="flex items-center gap-2 text-[10px] font-bold uppercase text-muted-foreground tracking-widest">
                            <Database className="w-3 h-3" />
                            {t("learning.editor.variables")}
                        </div>
                        <div className="space-y-2">
                            {Object.entries(variables).length > 0 ? (
                                Object.entries(variables).map(([key, value]) => (
                                    <div key={key} className="p-2 bg-muted/20 rounded-lg border border-muted/30 group hover:bg-muted/30 transition-colors">
                                        <div className="flex items-center justify-between mb-1">
                                            <div className="flex items-center gap-1.5">
                                                {getVarIcon(value)}
                                                <span className="font-mono text-[11px] font-bold text-muted-foreground tracking-tight underline decoration-primary/20 decoration-2 underline-offset-4">{key}</span>
                                            </div>
                                            <Badge variant="outline" className="text-[8px] h-3.5 px-1 py-0 opacity-50 uppercase font-black">
                                                {typeof value}
                                            </Badge>
                                        </div>
                                        <div className="text-[11px] pl-4 border-l border-primary/10 py-0.5">
                                            {renderValue(value)}
                                        </div>
                                    </div>
                                ))
                            ) : (
                                <div className="text-[10px] text-muted-foreground italic bg-muted/20 p-2 rounded-lg border border-dashed text-center">
                                    {t("learning.editor.noVariables")}
                                </div>
                            )}
                        </div>
                    </div>
                </div>
            </ScrollArea>

            {/* Footer Status */}
            <div className="p-3 border-t bg-muted/5">
                <div className="flex items-center justify-between text-[10px] font-bold">
                    <span className="text-muted-foreground uppercase opacity-50">{t("common.status.title")}</span>
                    <div className="flex items-center gap-1.5">
                        <div className={`w-2 h-2 rounded-full ${status === "running" ? "bg-emerald-500 animate-pulse" : "bg-muted-foreground/30"}`} />
                        <span className={status === "running" ? "text-emerald-500" : "text-muted-foreground"}>
                            {status === "running" ? t("common.status.active") : t("common.status.idle")}
                        </span>
                    </div>
                </div>
            </div>
        </Card>
    );
};
