import { useState } from "react"
import {
  HumanRequestCard as SharedHumanRequestCard,
  type HumanRequestItem,
} from "@evoloop/shared"
import { useAgentStore } from "@/stores/agentStore"
import { useProjectStore, type Project } from "@/stores/projectStore"
import { ProjectSwitcher } from "@/components/Sidebar/ProjectSwitcher"
import { MessageContent } from "./MessageContent"

export interface HumanRequestCardProps {
  request: HumanRequestItem
}

/**
 * 智能对话 (Chat) 容器适配层：
 * 接入 @evoloop/shared 的通用受控 HumanRequestCard，并注入 Chat 专属的 AgentStore 与 ProjectStore
 */
export function HumanRequestCard({ request }: HumanRequestCardProps) {
  const { resumeAgent, cancelHumanRequest } = useAgentStore()
  const setProject = useProjectStore((s) => s.setProject)
  const [showProjectSwitcher, setShowProjectSwitcher] = useState(false)

  const handleResponse = async (
    response: string,
    grantMode?: "once" | "always" | "default",
  ) => {
    await resumeAgent(response, grantMode)
  }

  const handleCancel = async () => {
    await cancelHumanRequest()
  }

  return (
    <SharedHumanRequestCard
      request={request}
      onRespond={handleResponse}
      onCancel={handleCancel}
      renderContent={(content) => <MessageContent content={content} />}
      renderProjectSwitcher={({ onSelect, disabled }) => (
        <>
          <button
            type="button"
            onClick={() => setShowProjectSwitcher(true)}
            disabled={disabled}
            className="w-full h-11 px-3 border-dashed border-2 rounded-lg text-xs font-semibold text-muted-foreground hover:text-foreground hover:border-primary/40 hover:bg-primary/5 transition-all flex items-center justify-start gap-2.5"
          >
            <span>选择目标项目…</span>
          </button>
          <ProjectSwitcher
            open={showProjectSwitcher}
            onOpenChange={setShowProjectSwitcher}
            onSelect={(proj: Project) => {
              setShowProjectSwitcher(false)
              const isTemporary = request.payload?.temporary === true
              if (!isTemporary) {
                setProject(proj)
              }
              onSelect(proj)
            }}
          />
        </>
      )}
    />
  )
}
