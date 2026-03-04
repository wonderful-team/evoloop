/**
 * InterruptedBanner - Displays a banner when Agent is paused for human input
 *
 * Supports multiple interaction types:
 * - text_input: Traditional text input (default)
 * - project_switch: Project selection with switcher
 * - confirm: Yes/No confirmation dialog
 */

import { AlertCircle, Play, XCircle, FolderGit2, CheckCircle2 } from "lucide-react"
import { useState, useCallback } from "react"
import { useTranslation } from "react-i18next"
import { Button } from "@evoloop/shared/components/ui/button"
import { Textarea } from "@evoloop/shared/components/ui/textarea"
import { useChatStore } from "@/stores/chatStore"
import { useProjectStore } from "@/stores/projectStore"
import { cn } from "@evoloop/shared/lib/utils"

export function InterruptedBanner() {
  const { t } = useTranslation()
  const status = useChatStore((s) => s.status)
  const humanRequest = useChatStore((s) => s.humanRequest)
  const resumeAgent = useChatStore((s) => s.resumeAgent)
  const stopAgent = useChatStore((s) => s.stopAgent)

  // Project switcher state
  const projects = useProjectStore((s) => s.projects)
  const setProject = useProjectStore((s) => s.setProject)
  const [selectedProjectId, setSelectedProjectId] = useState<number | null>(null)
  const [showProjectList, setShowProjectList] = useState(false)

  // Text input state
  const [showInput, setShowInput] = useState(false)
  const [userInput, setUserInput] = useState("")

  // Common state
  const [isSubmitting, setIsSubmitting] = useState(false)

  if (status !== "interrupted") return null
  // Get interaction type from humanRequest
  const interactionType = humanRequest?.type || "text_input"
  const prompt = humanRequest?.prompt || t("chat.interrupted.description")
  const allowCancel = humanRequest?.allow_cancel !== false

  const handleResume = useCallback(async () => {
    setIsSubmitting(true)
    try {
      // Check if this is a temporary project switch (Scheme C)
      const isTemporary = humanRequest?.payload?.temporary === true

      if (interactionType === "project_switch" && selectedProjectId !== null) {
        if (isTemporary) {
          // Scheme C: Temporary project - pass project_id via user_input (JSON format)
          const selectedProject = projects.find((p) => p.id === selectedProjectId)
          const tempContext = {
            type: "temp_project",
            project_id: selectedProjectId,
            project_name: selectedProject?.name,
          }
          await resumeAgent(JSON.stringify(tempContext))
        } else {
          // Scheme A: Full project switch
          const selectedProject = projects.find((p) => p.id === selectedProjectId)
          if (selectedProject) {
            setProject(selectedProject)
          }
          await resumeAgent(showInput ? userInput : undefined)
        }
      } else {
        await resumeAgent(showInput ? userInput : undefined)
      }
      // Reset state
      setShowInput(false)
      setUserInput("")
      setSelectedProjectId(null)
      setShowProjectList(false)
    } finally {
      setIsSubmitting(false)
    }
  }, [
    interactionType,
    selectedProjectId,
    projects,
    setProject,
    resumeAgent,
    showInput,
    userInput,
    humanRequest,
  ])

  const handleCancel = useCallback(async () => {
    setIsSubmitting(true)
    try {
      await stopAgent()
    } finally {
      setIsSubmitting(false)
    }
  }, [stopAgent])

  // Filter out global project and disconnected projects for project switch
  const availableProjects = projects.filter(
    (p) => p.id !== 0 && p.exists_locally !== false
  )

  // Render different content based on interaction type
  const renderContent = () => {
    switch (interactionType) {
      case "project_switch":
        return (
          <div className="space-y-3">
            <p className="text-sm text-muted-foreground">{prompt}</p>

            {!showProjectList ? (
              <Button
                variant="outline"
                onClick={() => setShowProjectList(true)}
                className="w-full justify-start gap-2"
                disabled={isSubmitting}
              >
                <FolderGit2 className="h-4 w-4" />
                {t("chat.interrupted.selectProject", "Select a Project...")}
              </Button>
            ) : (
              <div className="space-y-2">
                <p className="text-xs text-muted-foreground">
                  {t("chat.interrupted.chooseProject", "Choose a project to continue:")}
                </p>
                <div className="max-h-[200px] overflow-y-auto space-y-1 border rounded-md p-2">
                  {availableProjects.length === 0 ? (
                    <p className="text-sm text-muted-foreground text-center py-4">
                      {t("chat.interrupted.noProjects", "No available projects")}
                    </p>
                  ) : (
                    availableProjects.map((project) => (
                      <button
                        key={project.id}
                        onClick={() => setSelectedProjectId(project.id)}
                        disabled={isSubmitting}
                        className={cn(
                          "w-full text-left px-3 py-2 rounded-md text-sm transition-colors",
                          "hover:bg-accent hover:text-accent-foreground",
                          selectedProjectId === project.id
                            ? "bg-primary/10 text-primary border border-primary/30"
                            : "border border-transparent"
                        )}
                      >
                        <div className="flex items-center justify-between">
                          <span className="font-medium">{project.name}</span>
                          {selectedProjectId === project.id && (
                            <CheckCircle2 className="h-4 w-4 text-primary" />
                          )}
                        </div>
                        {project.path && (
                          <p className="text-xs text-muted-foreground truncate">
                            {project.path}
                          </p>
                        )}
                      </button>
                    ))
                  )}
                </div>
                {selectedProjectId && (
                  <p className="text-xs text-green-600 flex items-center gap-1">
                    <CheckCircle2 className="h-3 w-3" />
                    {t("chat.interrupted.projectSelected", "Project selected. Click Resume to continue.")}
                  </p>
                )}
              </div>
            )}
          </div>
        )

      case "confirm":
        return (
          <div className="space-y-3">
            <p className="text-sm text-muted-foreground">{prompt}</p>
            <div className="flex items-center gap-2 p-3 bg-amber-500/5 rounded-md border border-amber-500/20">
              <AlertCircle className="h-5 w-5 text-amber-500 shrink-0" />
              <span className="text-sm">{humanRequest?.payload?.confirm_text || t("chat.interrupted.confirmQuestion")}</span>
            </div>
          </div>
        )

      case "text_input":
      default:
        return (
          <>
            <p className="text-xs text-muted-foreground mt-1">{prompt}</p>

            {/* Optional Input Area */}
            {showInput && (
              <div className="mt-3">
                <Textarea
                  value={userInput}
                  onChange={(e) => setUserInput(e.target.value)}
                  placeholder={t(
                    "chat.interrupted.inputPlaceholder",
                    "Enter additional instructions (optional)...",
                  )}
                  className="text-sm min-h-[60px]"
                />
              </div>
            )}

            {!showInput && interactionType === "text_input" && (
              <Button
                size="sm"
                variant="outline"
                onClick={() => setShowInput(true)}
                disabled={isSubmitting}
                className="mt-2"
              >
                {t("chat.interrupted.addInput", "Add Instructions")}
              </Button>
            )}
          </>
        )
    }
  }

  // Get title based on interaction type
  const getTitle = () => {
    switch (interactionType) {
      case "project_switch":
        return t("chat.interrupted.projectSwitchTitle", "Project Switch Required")
      case "confirm":
        return t("chat.interrupted.confirmTitle", "Confirmation Required")
      case "text_input":
      default:
        return t("chat.interrupted.title", "Agent Paused")
    }
  }

  // Get resume button text
  const getResumeText = () => {
    switch (interactionType) {
      case "project_switch":
        return selectedProjectId
          ? t("chat.interrupted.resumeWithProject", "Resume with Selected Project")
          : t("chat.interrupted.resume", "Resume")
      case "confirm":
        return humanRequest?.payload?.confirm_text || t("chat.interrupted.confirm", "Confirm")
      default:
        return t("chat.interrupted.resume", "Resume")
    }
  }

  // Check if resume should be disabled
  const isResumeDisabled = () => {
    if (isSubmitting) return true
    if (interactionType === "project_switch" && selectedProjectId === null) return true
    return false
  }

  return (
    <div className="bg-amber-500/10 border border-amber-500/30 rounded-lg p-4 mx-4 mb-4 animate-in fade-in slide-in-from-top-2">
      <div className="flex items-start gap-3">
        <AlertCircle className="h-5 w-5 text-amber-500 shrink-0 mt-0.5" />
        <div className="flex-1 min-w-0">
          <h4 className="font-medium text-sm text-foreground">{getTitle()}</h4>

          {/* Dynamic Content */}
          <div className="mt-2">{renderContent()}</div>

          {/* Action Buttons */}
          <div className="flex items-center gap-2 mt-4">
            <Button
              size="sm"
              onClick={handleResume}
              disabled={isResumeDisabled()}
              className="gap-1.5"
            >
              <Play className="h-3.5 w-3.5" />
              {getResumeText()}
            </Button>

            {allowCancel && (
              <Button
                size="sm"
                variant="ghost"
                onClick={handleCancel}
                disabled={isSubmitting}
                className="gap-1.5 text-destructive hover:text-destructive"
              >
                <XCircle className="h-3.5 w-3.5" />
                {humanRequest?.payload?.cancel_text ||
                  t("chat.interrupted.cancel", "Cancel")}
              </Button>
            )}
          </div>
        </div>
      </div>
    </div>
  )
}
