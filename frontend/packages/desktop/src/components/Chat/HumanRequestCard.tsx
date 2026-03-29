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
        <Card className="w-full my-2 border-amber-500/30 bg-amber-500/5 shadow-sm animate-in fade-in slide-in-from-bottom-2">
            <CardHeader className="pb-2">
                <CardTitle className="text-sm font-medium flex items-center gap-2 text-amber-600 dark:text-amber-500">
                    <MessageCircleQuestion className="h-4 w-4" />
                    {t("chat.request.title")}
                </CardTitle>
            </CardHeader>

            <CardContent className="space-y-4">
                {/* Prompt */}
                <div className="font-medium">
                    <MessageContent content={request.prompt} />
                </div>

                {/* Context */}
                {request.context && (
                    <div className="bg-background/50 p-2 rounded border overflow-auto">
                        <MessageContent content={request.context} />
                    </div>
                )}

                {/* Inputs based on Type */}

                {/* Text Input */}
                {(request.type === "text" || request.type === "text_input") && (
                    <Textarea
                        value={input}
                        onChange={(e) => setInput(e.target.value)}
                        placeholder={t("chat.request.placeholder", "Enter your response...")}
                        className="min-h-[80px]"
                    />
                )}

                {/* Choice Input */}
                {request.type === "choice" && request.options && (
                    <RadioGroup value={input} onValueChange={setInput}>
                        {request.options.map((opt, i) => (
                            <div key={i} className="flex items-center space-x-2">
                                <RadioGroupItem value={opt} id={`opt-${i}`} />
                                <Label htmlFor={`opt-${i}`}>{opt}</Label>
                            </div>
                        ))}
                    </RadioGroup>
                )}
                
                {/* Project Switch Input */}
                {request.type === "project_switch" && (
                    <div className="space-y-3">
                        {!selectedProject ? (
                            <>
                                <Button
                                    variant="outline"
                                    onClick={() => setShowProjectSwitcher(true)}
                                    className="w-full justify-start gap-2"
                                    disabled={isSubmitting}
                                >
                                    <FolderGit2 className="h-4 w-4" />
                                    {t("chat.interrupted.selectProject", "Select Project")}
                                </Button>
                                {/* External ProjectSwitcher Dialog */}
                                <ProjectSwitcher 
                                    open={showProjectSwitcher}
                                    onOpenChange={setShowProjectSwitcher}
                                    onSelect={handleProjectSelect}
                                />
                            </>
                        ) : (
                            <div className="p-3 rounded-md border bg-primary/5 border-primary/20">
                                <p className="text-xs text-muted-foreground mb-1">
                                    {t("chat.interrupted.projectSelected", "Selected project")}:
                                </p>
                                <p className="font-medium text-sm">{selectedProject.name}</p>
                                {selectedProject.path && (
                                    <p className="text-xs text-muted-foreground truncate">
                                        {selectedProject.path}
                                    </p>
                                )}
                            </div>
                        )}
                    </div>
                )}
            </CardContent>

            <CardFooter className="flex justify-end gap-2 pt-0">
                {/* Cancel Button - Available for all request types */}
                <Button
                    variant="ghost"
                    size="sm"
                    onClick={handleCancel}
                    disabled={isSubmitting}
                    className="text-muted-foreground hover:text-destructive"
                >
                    <Ban className="mr-2 h-4 w-4" />
                    {t("common.cancel", "Cancel")}
                </Button>

                {/* Standard Submit for Text/Choice */}
                {(request.type === "text" || request.type === "text_input" || request.type === "choice") && (
                    <Button
                        onClick={() => handleResponse(input)}
                        disabled={isSubmitting || !input.trim()}
                        size="sm"
                    >
                        <Play className="mr-2 h-4 w-4" />
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
                            className="text-destructive hover:text-destructive"
                        >
                            <XCircle className="mr-2 h-4 w-4" />
                            {request.type === "approval" ? t("common.reject", "Reject") : t("common.no", "No")}
                        </Button>
                        <Button
                            size="sm"
                            onClick={() => handleResponse("yes")}
                            disabled={isSubmitting}
                        >
                            <CheckCircle2 className="mr-2 h-4 w-4" />
                            {request.type === "approval" ? t("common.approve", "Approve") : t("common.yes", "Yes")}
                        </Button>
                    </>
                )}
                
                {/* Project Switch - No extra button needed, auto-submits on selection */}
            </CardFooter>
        </Card>
    )
}
