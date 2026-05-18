import React from "react"
import { useTranslation } from "react-i18next"
import {
    Settings2,
    HelpCircle,
    Terminal,
    X,
    Plus,
    Type,
    Hash,
    CheckSquare,
    List as ListIcon,
    Trash2
} from "lucide-react"
import { Input } from "@evoloop/shared/components/ui/input"
import { Label } from "@evoloop/shared/components/ui/label"
import { Textarea } from "@evoloop/shared/components/ui/textarea"
import { Badge } from "@evoloop/shared/components/ui/badge"
import { Button } from "@evoloop/shared/components/ui/button"
import { ScrollArea } from "@evoloop/shared/components/ui/scroll-area"
import {
    Tooltip,
    TooltipContent,
    TooltipProvider,
    TooltipTrigger,
} from "@evoloop/shared/components/ui/tooltip"

export interface ParamDef {
    name: string
    type: string
    description: string
    required?: boolean
}

interface EditorSidebarProps {
    name: string
    setName: (val: string) => void
    description: string
    setDescription: (val: string) => void
    triggers: string[]
    newTrigger: string
    setNewTrigger: (val: string) => void
    handleAddTrigger: () => void
    handleRemoveTrigger: (index: number) => void
    params: ParamDef[]
    handleAddParam: () => void
    handleRemoveParam: (index: number) => void
    handleParamChange: (index: number, field: keyof ParamDef, value: string) => void
}

export const EditorSidebar: React.FC<EditorSidebarProps> = ({
    name,
    setName,
    description,
    setDescription,
    triggers,
    newTrigger,
    setNewTrigger,
    handleAddTrigger,
    handleRemoveTrigger,
    params,
    handleAddParam,
    handleRemoveParam,
    handleParamChange,
}) => {
    const { t } = useTranslation()

    return (
        <div className="w-[360px] border-r border-border flex flex-col bg-muted/5">
            <div className="h-[44px] px-3 border-b border-border bg-muted/10 flex items-center gap-2 shrink-0">
                <Settings2 className="h-4 w-4 text-primary" />
                <span className="text-[11px] font-bold uppercase tracking-widest text-muted-foreground/80">{t("learning.editor.configSidebar")}</span>
            </div>
            <ScrollArea className="flex-1">
                <div className="p-3 space-y-4 pb-6">
                    <section className="space-y-2">
                        <div className="flex items-center gap-2 mb-2">
                            <h3 className="text-[11px] font-bold uppercase tracking-widest text-muted-foreground/70">{t("learning.editor.skillName")}</h3>
                            <TooltipProvider>
                                <Tooltip>
                                    <TooltipTrigger asChild>
                                        <HelpCircle className="h-3.5 w-3.5 text-muted-foreground/40 cursor-help hover:text-primary transition-colors" />
                                    </TooltipTrigger>
                                    <TooltipContent side="right">
                                        {t("learning.editor.nameHelp")}
                                    </TooltipContent>
                                </Tooltip>
                            </TooltipProvider>
                        </div>
                        <Input
                            value={name}
                            onChange={(e) => setName(e.target.value)}
                            className="h-10 text-base font-medium bg-background border-muted focus-visible:ring-primary/30"
                        />

                        <div className="flex items-center gap-2 mb-1 pt-1">
                            <h3 className="text-[11px] font-bold uppercase tracking-widest text-muted-foreground/70">{t("learning.editor.skillDescription")}</h3>
                            <TooltipProvider>
                                <Tooltip>
                                    <TooltipTrigger asChild>
                                        <HelpCircle className="h-3.5 w-3.5 text-muted-foreground/40 cursor-help hover:text-primary transition-colors" />
                                    </TooltipTrigger>
                                    <TooltipContent side="right">
                                        {t("learning.editor.descHelp")}
                                    </TooltipContent>
                                </Tooltip>
                            </TooltipProvider>
                        </div>
                        <Textarea
                            value={description}
                            onChange={(e) => setDescription(e.target.value)}
                            rows={2}
                            className="bg-background border-muted focus-visible:ring-primary/30 min-h-[60px]"
                        />
                    </section>

                    <section className="space-y-2 p-3 bg-background/50 rounded-xl border border-muted-foreground/10">
                        <div className="flex items-center justify-between gap-2">
                            <h3 className="text-[11px] font-bold uppercase tracking-widest text-muted-foreground/70 flex items-center gap-2">
                                <Terminal className="h-4 w-4 text-primary" />
                                {t("learning.editor.triggerPatterns")}
                                <TooltipProvider>
                                    <Tooltip>
                                        <TooltipTrigger asChild>
                                            <HelpCircle className="h-3.5 w-3.5 text-muted-foreground/40 cursor-help hover:text-primary transition-colors" />
                                        </TooltipTrigger>
                                        <TooltipContent side="right">
                                            {t("learning.editor.triggerHelp")}
                                        </TooltipContent>
                                    </Tooltip>
                                </TooltipProvider>
                            </h3>
                            <Badge variant="secondary" className="text-[11px] opacity-60 font-mono">{triggers.length}</Badge>
                        </div>
                        <div className="flex flex-wrap gap-2 min-h-[32px] p-1">
                            {triggers.length === 0 && (
                                <span className="text-[10px] text-muted-foreground italic opacity-50">
                                    {t("learning.editor.noTriggers")}
                                </span>
                            )}
                            {triggers.map((trigger, i) => (
                                <Badge key={i} variant="secondary" className="pl-3 pr-1 py-1 gap-1 border border-primary/10 bg-background hover:border-primary/30 transition-all">
                                    {trigger}
                                    <Button variant="ghost" size="icon" className="h-4 w-4 rounded-full hover:bg-destructive hover:text-white" onClick={() => handleRemoveTrigger(i)}>
                                        <X className="h-2.5 w-2.5" />
                                    </Button>
                                </Badge>
                            ))}
                        </div>
                        <div className="flex gap-2">
                            <Input value={newTrigger} onChange={(e) => setNewTrigger(e.target.value)} placeholder={t("learning.editor.addTrigger")} className="h-9 text-xs bg-background border-muted/50" onKeyDown={(e) => e.key === "Enter" && handleAddTrigger()} />
                            <Button size="sm" variant="outline" className="h-9 w-9 p-0 border-muted/50" onClick={handleAddTrigger}><Plus className="h-4 w-4" /></Button>
                        </div>
                    </section>

                    <section className="space-y-4">
                        <div className="flex items-center justify-between border-b pb-2">
                            <h3 className="text-[11px] font-bold uppercase tracking-widest text-muted-foreground/70 flex items-center gap-2">
                                {t("learning.editor.parameters")}
                                <TooltipProvider>
                                    <Tooltip>
                                        <TooltipTrigger asChild>
                                            <HelpCircle className="h-3.5 w-3.5 text-muted-foreground/40 cursor-help hover:text-primary transition-colors" />
                                        </TooltipTrigger>
                                        <TooltipContent side="right">
                                            {t("learning.editor.paramHelp")}
                                        </TooltipContent>
                                    </Tooltip>
                                </TooltipProvider>
                            </h3>
                            <Button size="sm" variant="outline" className="h-7 text-[11px] gap-1 bg-primary/5 hover:bg-primary/10 border-primary/10 rounded-full px-3" onClick={handleAddParam}>
                                <Plus className="h-3 w-3" />
                                {t("learning.editor.addParameter")}
                            </Button>
                        </div>
                        <div className="space-y-2">
                            {params.length === 0 && (
                                <div className="py-6 px-3 border rounded-xl border-dashed bg-muted/5 flex flex-col items-center justify-center gap-2 opacity-50">
                                    <Type className="h-6 w-6 text-muted-foreground" />
                                    <span className="text-[11px] uppercase font-bold tracking-widest">{t("learning.execution.noParams")}</span>
                                </div>
                            )}
                            {params.map((param, i) => (
                                <div key={i} className="flex flex-col border rounded-xl bg-background shadow-sm transition-all hover:border-primary/30 group overflow-hidden">
                                    <div className="flex items-center justify-between p-3 bg-muted/20 border-b">
                                        <div className="flex items-center gap-2">
                                            <div className="p-1.5 bg-background rounded-lg border shadow-sm">
                                                {param.type === "number" ? <Hash className="h-3.5 w-3.5 text-primary" /> : param.type === "boolean" ? <CheckSquare className="h-3.5 w-3.5 text-primary" /> : param.type === "array" ? <ListIcon className="h-3.5 w-3.5 text-primary" /> : <Type className="h-3.5 w-3.5 text-primary" />}
                                            </div>
                                            <span className="text-xs font-bold">{param.name}</span>
                                        </div>
                                        <Button variant="ghost" size="icon" className="h-7 w-7 text-muted-foreground hover:text-destructive hover:bg-destructive/10" onClick={() => handleRemoveParam(i)}><Trash2 className="h-3.5 w-3.5" /></Button>
                                    </div>
                                    <div className="p-3 space-y-3">
                                        <div className="space-y-2">
                                            <Label className="text-[11px] font-bold uppercase text-muted-foreground/80 flex items-center gap-1">
                                                {t("learning.editor.paramDesc")}
                                                <TooltipProvider>
                                                    <Tooltip>
                                                        <TooltipTrigger asChild>
                                                            <HelpCircle className="h-3 w-3 text-muted-foreground/30 cursor-help" />
                                                        </TooltipTrigger>
                                                        <TooltipContent>{t("learning.editor.paramDescHelp")}</TooltipContent>
                                                    </Tooltip>
                                                </TooltipProvider>
                                            </Label>
                                            <Input value={param.description} onChange={(e) => { handleParamChange(i, "description", e.target.value); if (!param.name) { const autoName = e.target.value.toLowerCase().replace(/[^a-z0-9]/g, '_').replace(/_+/g, '_').substring(0, 20); handleParamChange(i, "name", autoName); } }} className="h-9 text-xs" />
                                        </div>
                                        <div className="grid grid-cols-2 gap-4">
                                            <div className="space-y-2">
                                                <Label className="text-[11px] font-bold uppercase text-muted-foreground/80 flex items-center gap-1">
                                                    {t("learning.editor.paramName")}
                                                    <TooltipProvider>
                                                        <Tooltip>
                                                            <TooltipTrigger asChild>
                                                                <HelpCircle className="h-3 w-3 text-muted-foreground/30 cursor-help" />
                                                            </TooltipTrigger>
                                                            <TooltipContent>{t("learning.editor.paramNameHelp")}</TooltipContent>
                                                        </Tooltip>
                                                    </TooltipProvider>
                                                </Label>
                                                <Input value={param.name} onChange={(e) => handleParamChange(i, "name", e.target.value)} className="h-9 text-xs font-mono bg-muted/20" />
                                            </div>
                                            <div className="space-y-2">
                                                <Label className="text-[11px] font-bold uppercase text-muted-foreground/80">{t("learning.editor.paramType")}</Label>
                                                <div className="flex gap-1">
                                                    {["string", "number", "boolean", "array"].map(type => (
                                                        <Button key={type} variant={param.type === type ? "secondary" : "outline"} size="icon" className={`h-8 w-8 ${param.type === type ? "bg-primary/20" : "opacity-60"}`} onClick={() => handleParamChange(i, "type", type)}>
                                                            {type === "number" ? <Hash className="h-3.5 w-3.5" /> : type === "boolean" ? <CheckSquare className="h-3.5 w-3.5" /> : type === "array" ? <ListIcon className="h-3.5 w-3.5" /> : <Type className="h-3.5 w-3.5" />}
                                                        </Button>
                                                    ))}
                                                </div>
                                            </div>
                                        </div>
                                    </div>
                                </div>
                            ))}
                        </div>
                    </section>
                </div>
            </ScrollArea>
        </div>
    )
}
