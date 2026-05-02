import { Play, XCircle, CheckCircle2, MessageCircleQuestion, Ban, FolderGit2 } from "lucide-react"
import { useState } from "react"
import { MessageContent } from "./MessageContent"
import { useTranslation } from "react-i18next"
import { Button } from "@evoloop/shared/components/ui/button"
import { Card, CardContent, CardFooter, CardHeader, CardTitle } from "@evoloop/shared/components/ui/card"
import { Textarea } from "@evoloop/shared/components/ui/textarea"
import { RadioGroup, RadioGroupItem } from "@evoloop/shared/components/ui/radio-group"
import { Label } from "@evoloop/shared/components/ui/label"
import { useChatStore } from "@/stores/chatStore"
import { useProjectStore, type Project } from "@/stores/projectStore"
import { ProjectSwitcher } from "@/components/Sidebar/ProjectSwitcher"

export interface HumanRequestCardProps {
    request: {
        id: string
        type: "text" | "choice" | "confirmation" | "approval" | "text_input" | "confirm" | "project_switch"
        prompt: string
        options?: string[]
        context?: string
        payload?: {
            allow_global?: boolean
            suggested_project_id?: number
            show_project_list?: boolean
            temporary?: boolean
        }
        status?: "waiting_human" | "completed" | "cancelled"
    }
}

export function HumanRequestCard({ request }: HumanRequestCardProps) {
    const { t } = useTranslation()
    const resumeAgent = useChatStore((s) => s.resumeAgent)
    const cancelHumanRequest = useChatStore((s) => s.cancelHumanRequest)
    const setProject = useProjectStore((s) => s.setProject)
    const [input, setInput] = useState("")
    const [isSubmitting, setIsSubmitting] = useState(false)
    
    // Project switch state
    const [showProjectSwitcher, setShowProjectSwitcher] = useState(false)
    const [selectedProject, setSelectedProject] = useState<Project | null>(null)

    const handleResponse = async (response: string) => {
        setIsSubmitting(true)
        try {
            await resumeAgent(response)
        } finally {
            setIsSubmitting(false)
        }
    }
    
    const handleProjectSelect = async (project: Project) => {
        setSelectedProject(project)
        setShowProjectSwitcher(false)
        
        setIsSubmitting(true)
        try {
            // Check if this is a temporary project switch (Scheme C)
            const isTemporary = request.payload?.temporary === true
            
            if (isTemporary) {
                // Scheme C: Pass project info via JSON
                const tempContext = {
                    type: "temp_project",
                    project_id: project.id,
                    project_name: project.name,
                }
                await resumeAgent(JSON.stringify(tempContext))
            } else {
                // Scheme A: Full project switch - set project in store and pass project_id
                setProject(project)
                await resumeAgent(String(project.id))
            }
        } finally {
            setIsSubmitting(false)
        }
    }

    const handleCancel = async () => {
        setIsSubmitting(true)
        try {
            await cancelHumanRequest()
        } finally {
            setIsSubmitting(false)
        }
    }

    return (
        <div className="w-full my-6 animate-in fade-in slide-in-from-top-2 duration-500">
            {/* Header: Task Action Required */}
            <div className="flex items-center gap-2 mb-4 px-3 py-1.5 bg-amber-500/5 border-l-2 border-amber-500 rounded-r-md">
                <MessageCircleQuestion className="h-4 w-4 text-amber-500" />
                <span className="text-[11px] font-bold uppercase tracking-widest text-amber-600/80">
                    {t("chat.request.title")}
                </span>
            </div>

            <div className="pl-4 space-y-5">
                {/* Prompt - The main question/instruction */}
                <div className="text-[15px] font-medium leading-relaxed border-l border-border/40 pl-4 py-1">
                    <MessageContent content={request.prompt} />
                </div>

                {/* Context - Extra info, rendered as a sub-document callout */}
                {request.context && (
                    <div className="bg-muted/30 p-4 rounded-lg border border-[var(--doc-border)] text-xs font-mono leading-loose">
                        <div className="flex items-center gap-2 mb-2 opacity-40 uppercase tracking-tighter font-bold">
                            <BookOpen size={12} />
                            Contextual Reference
                        </div>
                        <MessageContent content={request.context} />
                    </div>
                )}

                {/* Interactive Inputs */}
                <div className="bg-background border border-[var(--doc-border)] rounded-xl p-6 shadow-sm">
                    {/* Inputs based on Type */}
                    <div className="mb-6">
                        {/* Text Input */}
                        {(request.type === "text" || request.type === "text_input") && (
                            <Textarea
                                value={input}
                                onChange={(e) => setInput(e.target.value)}
                                placeholder={t("chat.request.placeholder", "Enter your response...")}
                                className="min-h-[120px] bg-muted/20 border-none focus-visible:ring-1 focus-visible:ring-primary/20 resize-none text-sm"
                            />
                        )}

                        {/* Choice Input */}
                        {request.type === "choice" && request.options && (
                            <RadioGroup value={input} onValueChange={setInput} className="gap-3">
                                {request.options.map((opt, i) => (
                                    <div key={i} className="flex items-center space-x-3 p-3 rounded-lg border border-transparent hover:border-primary/20 hover:bg-primary/5 transition-all cursor-pointer group">
                                        <RadioGroupItem value={opt} id={`opt-${i}`} className="border-primary/20" />
                                        <Label htmlFor={`opt-${i}`} className="text-sm font-medium cursor-pointer flex-1">{opt}</Label>
                                    </div>
                                ))}
                            </RadioGroup>
                        )}
                        
                        {/* Project Switch Input */}
                        {request.type === "project_switch" && (
                            <div className="space-y-4">
                                {!selectedProject ? (
                                    <>
                                        <Button
                                            variant="outline"
                                            onClick={() => setShowProjectSwitcher(true)}
                                            className="w-full h-12 justify-start gap-3 border-dashed border-2 hover:border-primary/40 hover:bg-primary/5 transition-all"
                                            disabled={isSubmitting}
                                        >
                                            <FolderGit2 className="h-5 w-5 text-primary/60" />
                                            <span className="font-semibold">{t("chat.interrupted.selectProject", "Select Project")}</span>
                                        </Button>
                                        <ProjectSwitcher 
                                            open={showProjectSwitcher}
                                            onOpenChange={setShowProjectSwitcher}
                                            onSelect={handleProjectSelect}
                                        />
                                    </>
                                ) : (
                                    <div className="p-4 rounded-xl border bg-primary/5 border-primary/20 flex items-center gap-4">
                                        <div className="p-3 bg-primary/10 rounded-full">
                                            <FolderGit2 className="h-5 w-5 text-primary" />
                                        </div>
                                        <div className="flex-1 min-w-0">
                                            <p className="text-[10px] uppercase font-bold text-primary/60 tracking-wider mb-0.5">
                                                {t("chat.interrupted.projectSelected", "Selected project")}
                                            </p>
                                            <p className="font-bold text-sm truncate">{selectedProject.name}</p>
                                            {selectedProject.path && (
                                                <p className="text-[10px] text-muted-foreground/60 truncate font-mono mt-0.5">
                                                    {selectedProject.path}
                                                </p>
                                            )}
                                        </div>
                                    </div>
                                )}
                            </div>
                        )}
                    </div>

                    {/* Action Footer - Only show if pending */}
                    <div className="flex justify-end items-center gap-4 border-t border-border/30 pt-6">
                        {(!request.status || request.status === "waiting_human") ? (
                            <>
                                <Button
                                    variant="ghost"
                                    size="sm"
                                    onClick={handleCancel}
                                    disabled={isSubmitting}
                                    className="text-muted-foreground/60 hover:text-destructive hover:bg-destructive/5 font-bold uppercase tracking-wider text-[10px]"
                                >
                                    <Ban className="mr-2 h-3.5 w-3.5" />
                                    {t("common.cancel", "Cancel")}
                                </Button>
                                <div className="flex gap-2">
                                    {/* Standard Submit for Text/Choice */}
                                    {(request.type === "text" || request.type === "text_input" || request.type === "choice") && (
                                        <Button
                                            onClick={() => handleResponse(input)}
                                            disabled={isSubmitting || !input.trim()}
                                            size="sm"
                                            className="px-6 rounded-full font-bold shadow-lg shadow-primary/20"
                                        >
                                            <Play className="mr-2 h-3.5 w-3.5" />
                                            {t("common.submit", "Submit")}
                                        </Button>
                                    )}

                                    {/* Confirmation Buttons */}
                                    {(request.type === "confirmation" || request.type === "confirm" || request.type === "approval") && (
                                        <>
                                            <Button
                                                variant="outline"
                                                size="sm"
                                                onClick={() => handleResponse("no")}
                                                disabled={isSubmitting}
                                                className="rounded-full px-6 border-destructive/20 text-destructive hover:bg-destructive/5 font-bold"
                                            >
                                                <XCircle className="mr-2 h-3.5 w-3.5" />
                                                {request.type === "approval" ? t("common.reject", "Reject") : t("common.no", "No")}
                                            </Button>
                                            <Button
                                                size="sm"
                                                onClick={() => handleResponse("yes")}
                                                disabled={isSubmitting}
                                                className="rounded-full px-6 shadow-lg shadow-primary/20 font-bold"
                                            >
                                                <CheckCircle2 className="mr-2 h-3.5 w-3.5" />
                                                {request.type === "approval" ? t("common.approve", "Approve") : t("common.yes", "Yes")}
                                            </Button>
                                        </>
                                    )}
                                </div>
                            </>
                        ) : (
                            <div className={`flex items-center gap-2 px-4 py-1.5 rounded-full text-[10px] font-bold uppercase tracking-widest ${
                                request.status === "completed" 
                                    ? "bg-emerald-500/10 text-emerald-500 border border-emerald-500/20" 
                                    : "bg-destructive/10 text-destructive border border-destructive/20"
                            }`}>
                                {request.status === "completed" ? (
                                    <>
                                        <CheckCircle2 className="h-3 w-3" />
                                        {t("chat.request.completed", "Completed")}
                                    </>
                                ) : (
                                    <>
                                        <XCircle className="h-3 w-3" />
                                        {t("chat.request.cancelled", "Cancelled")}
                                    </>
                                )}
                            </div>
                        )}
                    </div>
                </div>
            </div>
        </div>
    )
}
