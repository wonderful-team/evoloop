import { Button } from "@evoloop/shared/components/ui/button"
import { Checkbox } from "@evoloop/shared/components/ui/checkbox"
import { Label } from "@evoloop/shared/components/ui/label"
import {
  RadioGroup,
  RadioGroupItem,
} from "@evoloop/shared/components/ui/radio-group"
import { Textarea } from "@evoloop/shared/components/ui/textarea"
import { Ban, CheckCircle2, FolderGit2, Play, XCircle } from "lucide-react"
import { useState } from "react"
import { useTranslation } from "react-i18next"
import { ProjectSwitcher } from "@/components/Sidebar/ProjectSwitcher"
import { useAgentStore } from "@/stores/agentStore"
import { type Project, useProjectStore } from "@/stores/projectStore"
import { MessageContent } from "./MessageContent"

export interface HumanRequestCardProps {
  request: {
    id: string
    type:
      | "text"
      | "choice"
      | "multi_choice"
      | "confirmation"
      | "approval"
      | "project_switch"
      | "file_select"
    prompt: string
    options?: string[]
    context?: string
    payload?: {
      allow_global?: boolean
      suggested_project_id?: number
      show_project_list?: boolean
      temporary?: boolean
      multiple?: boolean
      file_types?: string[]
    }
    status?: "waiting_human" | "completed" | "cancelled"
  }
}

export function HumanRequestCard({ request }: HumanRequestCardProps) {
  const { t } = useTranslation()
  const { resumeAgent, cancelHumanRequest } = useAgentStore()
  const setProject = useProjectStore((s) => s.setProject)
  const [input, setInput] = useState("")
  const [customValue, setCustomValue] = useState("")
  const [selected, setSelected] = useState<string[]>([])
  const [customEnabled, setCustomEnabled] = useState(false)
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
    <div className="w-full my-2 animate-in fade-in slide-in-from-top-2 duration-500">
      <div className="space-y-2">
        {/* Prompt - The main question/instruction */}
        <div className="text-[14px] font-medium leading-relaxed border-l-2 border-primary/40 pl-3 py-0.5">
          <MessageContent content={request.prompt} />
        </div>

        {/* Context - Extra info, rendered as a sub-document callout */}
        {request.context && (
          <div className="bg-muted/30 p-2.5 px-3 rounded-md border border-[var(--doc-border)] text-xs font-mono leading-relaxed">
            <MessageContent content={request.context} />
          </div>
        )}

        {/* Interactive Inputs */}
        <div className="bg-background border border-[var(--doc-border)] rounded-lg p-2">
          {/* Inputs based on Type */}
          <div className="mb-2">
            {/* Text Input */}
            {request.type === "text" && (
              <Textarea
                value={input}
                onChange={(e) => setInput(e.target.value)}
                placeholder={t("chat.request.placeholder")}
                className="min-h-[80px] bg-muted/20 border-none focus-visible:ring-1 focus-visible:ring-primary/20 resize-none text-sm"
              />
            )}

            {/* Choice Input */}
            {request.type === "choice" && request.options && (
              <div className="space-y-2">
                <RadioGroup
                  value={input}
                  onValueChange={setInput}
                  className="gap-1.5"
                >
                  {request.options.map((opt, i) => (
                    <div
                      key={i}
                      className="flex items-center space-x-2.5 p-1.5 px-2 rounded-md border border-transparent hover:border-primary/20 hover:bg-primary/5 transition-all cursor-pointer group"
                    >
                      <RadioGroupItem
                        value={opt}
                        id={`opt-${i}`}
                        className="border-primary/20 shrink-0 mt-0.5"
                      />
                      <Label
                        htmlFor={`opt-${i}`}
                        className="text-[13px] font-medium cursor-pointer flex-1 leading-relaxed break-words"
                      >
                        {opt}
                      </Label>
                    </div>
                  ))}
                  {/* 自定义输入选项（每次都带） */}
                  <div className="flex items-center space-x-2.5 p-1.5 px-2 rounded-md border border-transparent hover:border-primary/20 hover:bg-primary/5 transition-all cursor-pointer group">
                    <RadioGroupItem
                      value="__custom__"
                      id="opt-custom"
                      className="border-primary/20 shrink-0 mt-0.5"
                    />
                    <Label
                      htmlFor="opt-custom"
                      className="text-[13px] font-medium cursor-pointer flex-1 leading-relaxed break-words"
                    >
                      {t("common.customInput")}
                    </Label>
                  </div>
                </RadioGroup>
                {/* 选中自定义输入时显示输入框 */}
                {input === "__custom__" && (
                  <Textarea
                    value={customValue}
                    onChange={(e) => setCustomValue(e.target.value)}
                    placeholder={t("common.customInputPlaceholder")}
                    className="min-h-[60px] bg-muted/20 border-none focus-visible:ring-1 focus-visible:ring-primary/20 resize-none text-sm"
                  />
                )}
              </div>
            )}

            {/* Multi Choice Input (勾选多项) */}
            {request.type === "multi_choice" && request.options && (
              <div className="space-y-2">
                {request.options.map((opt, i) => (
                  <div
                    key={i}
                    className="flex items-center space-x-2.5 p-1.5 px-2 rounded-md border border-transparent hover:border-primary/20 hover:bg-primary/5 transition-all cursor-pointer group"
                  >
                    <Checkbox
                      id={`mopt-${i}`}
                      checked={selected.includes(opt)}
                      onCheckedChange={(c) => {
                        if (c) {
                          setSelected((s) => [...s, opt])
                        } else {
                          setSelected((s) => s.filter((x) => x !== opt))
                        }
                      }}
                      className="border-primary/20 shrink-0 mt-0.5"
                    />
                    <Label
                      htmlFor={`mopt-${i}`}
                      className="text-[13px] font-medium cursor-pointer flex-1 leading-relaxed break-words"
                    >
                      {opt}
                    </Label>
                  </div>
                ))}
                {/* 自定义输入选项（可选） */}
                <div className="flex items-center space-x-2.5 p-1.5 px-2 rounded-md border border-transparent hover:border-primary/20 hover:bg-primary/5 transition-all cursor-pointer group">
                  <Checkbox
                    id="mopt-custom"
                    checked={customEnabled}
                    onCheckedChange={(c) => setCustomEnabled(c === true)}
                    className="border-primary/20 shrink-0 mt-0.5"
                  />
                  <Label
                    htmlFor="mopt-custom"
                    className="text-[13px] font-medium cursor-pointer flex-1 leading-relaxed break-words"
                  >
                    {t("common.customInput")}
                  </Label>
                </div>
                {customEnabled && (
                  <Textarea
                    value={customValue}
                    onChange={(e) => setCustomValue(e.target.value)}
                    placeholder={t("common.customInputPlaceholder")}
                    className="min-h-[60px] bg-muted/20 border-none focus-visible:ring-1 focus-visible:ring-primary/20 resize-none text-sm"
                  />
                )}
              </div>
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
                      <span className="font-semibold">
                        {t("chat.interrupted.selectProject")}
                      </span>
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
                        {t("chat.interrupted.selectedProject")}
                      </p>
                      <p className="font-bold text-sm truncate">
                        {selectedProject.name}
                      </p>
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

            {/* File Select Input */}
            {request.type === "file_select" && (
              <div className="space-y-4">
                <Button
                  variant="outline"
                  onClick={() => {
                    // Trigger system file picker via a hidden input or bridge
                    const input = document.createElement("input")
                    input.type = "file"
                    input.multiple = request.payload?.multiple || false
                    if (request.payload?.file_types) {
                      input.accept = request.payload.file_types.join(",")
                    }
                    input.onchange = (e) => {
                      const files = (e.target as HTMLInputElement).files
                      if (files && files.length > 0) {
                        const paths = Array.from(files)
                          .map((f) => (f as any).path || f.name)
                          .join(", ")
                        setInput(paths)
                      }
                    }
                    input.click()
                  }}
                  className="w-full h-12 justify-start gap-3 border-dashed border-2 hover:border-primary/40 hover:bg-primary/5 transition-all"
                  disabled={isSubmitting}
                >
                  <FolderGit2 className="h-5 w-5 text-primary/60" />
                  <span className="font-semibold">
                    {input || t("chat.request.selectFiles")}
                  </span>
                </Button>
              </div>
            )}
          </div>

          {/* Action Footer - Only show if pending */}
          <div className="flex justify-end items-center gap-3 border-t border-border/30 pt-2 mt-2">
            {!request.status || request.status === "waiting_human" ? (
              <>
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={handleCancel}
                  disabled={isSubmitting}
                  className="h-8 text-muted-foreground/60 hover:text-destructive hover:bg-destructive/5 font-bold uppercase tracking-wider text-[10px] px-3"
                >
                  <Ban className="mr-1.5 h-3.5 w-3.5" />
                  {t("common.cancel")}
                </Button>
                <div className="flex gap-2">
                  {/* Standard Submit for Text/Choice/MultiChoice/File */}
                  {(request.type === "text" ||
                    request.type === "choice" ||
                    request.type === "multi_choice" ||
                    request.type === "file_select") && (
                    <Button
                      onClick={() =>
                        handleResponse(
                          request.type === "choice" && input === "__custom__"
                            ? customValue
                            : request.type === "multi_choice"
                              ? [
                                  ...selected,
                                  ...(customEnabled && customValue.trim()
                                    ? customValue
                                        .split(/[,，\s]+/)
                                        .filter(Boolean)
                                    : []),
                                ].join(",")
                              : input,
                        )
                      }
                      disabled={
                        isSubmitting ||
                        (request.type === "choice" && input === "__custom__"
                          ? !customValue.trim()
                          : request.type === "multi_choice"
                            ? selected.length === 0 &&
                              !(customEnabled && customValue.trim())
                            : !input.trim())
                      }
                      size="sm"
                      className="h-8 px-5 rounded-full font-bold text-xs"
                    >
                      <Play className="mr-1.5 h-3.5 w-3.5" />
                      {t("common.submit")}
                    </Button>
                  )}

                  {/* Confirmation Buttons */}
                  {(request.type === "confirmation" ||
                    request.type === "approval") && (
                    <>
                      <Button
                        variant="outline"
                        size="sm"
                        onClick={() => handleResponse("no")}
                        disabled={isSubmitting}
                        className="h-8 rounded-full px-5 border-destructive/20 text-destructive hover:bg-destructive/5 font-bold text-xs"
                      >
                        <XCircle className="mr-1.5 h-3.5 w-3.5" />
                        {request.type === "approval"
                          ? t("common.reject")
                          : t("common.no")}
                      </Button>
                      <Button
                        size="sm"
                        onClick={() => handleResponse("yes")}
                        disabled={isSubmitting}
                        className="h-8 rounded-full px-5 font-bold text-xs"
                      >
                        <CheckCircle2 className="mr-1.5 h-3.5 w-3.5" />
                        {request.type === "approval"
                          ? t("common.approve")
                          : t("common.yes")}
                      </Button>
                    </>
                  )}
                </div>
              </>
            ) : (
              <div
                className={`flex items-center gap-2 px-4 py-1.5 rounded-full text-[10px] font-bold uppercase tracking-widest ${
                  request.status === "completed"
                    ? "bg-emerald-500/10 text-emerald-500 border border-emerald-500/20"
                    : "bg-destructive/10 text-destructive border border-destructive/20"
                }`}
              >
                {request.status === "completed" ? (
                  <>
                    <CheckCircle2 className="h-3 w-3" />
                    {t("chat.request.completed")}
                  </>
                ) : (
                  <>
                    <XCircle className="h-3 w-3" />
                    {t("chat.request.cancelled")}
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
