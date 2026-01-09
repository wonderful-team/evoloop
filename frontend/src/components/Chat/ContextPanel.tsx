import {
  Bot,
  Brain,
  ChevronDown,
  ChevronRight,
  ChevronUp,
  Cpu,
  Database,
  Layers,
  LayoutDashboard,
  Loader2,
  Map as MapIcon,
  Wrench,
  X,
} from "lucide-react"
import { memo, useState, useEffect } from "react"
import { useTranslation } from "react-i18next"
import { Button } from "@/components/ui/button"
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs"
import { KnowledgeTab } from "./context/KnowledgeTab"
// Import Tab Components
import { MemoryTab } from "./context/MemoryTab"
import { PlanTab } from "./context/PlanTab"
import { ResourcesTab } from "./context/ResourcesTab"
import { StateTab } from "./context/StateTab"
import { ToolsTab } from "./context/ToolsTab"
// Import Agent Features
import { useChatStore } from "@/stores/chatStore"
import { cn } from "@/lib/utils"
import { ThoughtCard } from "./ThoughtCard"
import { TaskSteps } from "./TaskSteps"
import { ArtifactsList } from "./Artifacts/ArtifactsList"
import { MessageContent } from "./MessageContent"
import { HumanRequestCard } from "./HumanRequestCard"
import { ScrollArea } from "@/components/ui/scroll-area"

interface ContextPanelProps {
  projectId?: number
  activeThreadId?: string
  autoSwitchToTab?: string
  onClose?: () => void
}

/**
 * AgentWorkstation (formerly ContextPanel)
 * Integrates "Live Agent Execution" (Top) and "Static Context" (Bottom)
 */
export const ContextPanel = memo(
  ({ projectId, activeThreadId, autoSwitchToTab, onClose }: ContextPanelProps) => {
    const { t } = useTranslation()
    const [activeTab, setActiveTab] = useState("memory")
    const [isLiveZoneExpanded, setIsLiveZoneExpanded] = useState(true)

    // --- Store Selectors (from AgentCanvas) ---
    const streamedContent = useChatStore((s) => s.streamedContent)
    const tasks = useChatStore((s) => s.tasks)
    const artifacts = useChatStore((s) => s.artifacts)
    const status = useChatStore((s) => s.status)
    const agentState = useChatStore((s) => s.agentState)
    const thoughts = useChatStore((s) => s.thoughts) || []
    const humanRequest = useChatStore((s) => s.humanRequest)

    // Determine if Agent is active
    const isAgentActive = status === "running" || status === "interrupted" || status === "SUMMARIZING"

    // Auto-expand Live Zone when agent starts working
    useEffect(() => {
      if (isAgentActive) {
        setIsLiveZoneExpanded(true)
      }
    }, [isAgentActive])

    // Phase 5: Auto-switch Tab
    useEffect(() => {
      if (autoSwitchToTab) {
        setActiveTab(autoSwitchToTab)
      }
    }, [autoSwitchToTab])

    // Default to 'memory' if no auto-switch
    useEffect(() => {
      if (!autoSwitchToTab) {
        setActiveTab("memory")
      }
    }, [autoSwitchToTab])

    if (typeof projectId !== "number" || Number.isNaN(projectId)) {
      return (
        <div className="flex flex-col items-center justify-center h-full text-muted-foreground p-4 text-center">
          <Brain className="h-10 w-10 mb-2 opacity-20" />
          <p>{t("chat.context.selectProject")}</p>
        </div>
      )
    }

    return (
      <div className="flex flex-col h-full bg-background border-l">
        {/* Header (Unified) */}
        <div className="flex items-center justify-between p-3 border-b h-14 shrink-0">
          <span className="font-semibold text-sm flex items-center gap-2">
            {isAgentActive ? (
              <Loader2 className="h-4 w-4 text-primary animate-spin" />
            ) : (
              <LayoutDashboard className="h-4 w-4 text-muted-foreground" />
            )}
            {t("chat.context.title", "Agent Workstation")}
          </span>
          {onClose && (
            <Button
              variant="ghost"
              size="icon"
              className="h-7 w-7"
              onClick={onClose}
            >
              <X className="h-4 w-4" />
            </Button>
          )}
        </div>

        {/* TOP ZONE: Live Agent Activity (Collapsible) */}
        {(thoughts.length > 0 || isAgentActive || humanRequest) && (
          <div className="border-b transition-all duration-300 ease-in-out flex flex-col max-h-[50%] shrink-0">
            {/* Zone Header / Toggle */}
            <div
              className={cn(
                "flex items-center justify-between px-3 py-2 bg-muted/20 cursor-pointer hover:bg-muted/40 transition-colors",
                isLiveZoneExpanded && "border-b"
              )}
              onClick={() => setIsLiveZoneExpanded(!isLiveZoneExpanded)}
            >
              <div className="flex items-center gap-2 text-xs font-medium text-muted-foreground uppercase tracking-wider">
                <Bot size={12} />
                {t("chat.canvas.title", "Live Activity")}
                {status === "interrupted" && <span className="text-amber-500 font-bold ml-1">(WAITING INPUT)</span>}
              </div>
              {isLiveZoneExpanded ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
            </div>

            {/* Live Content Area */}
            {isLiveZoneExpanded && (
              <ScrollArea className="flex-1 bg-muted/5 min-h-[150px]">
                <div className="p-3 space-y-4">
                  {/* HITL Request Card */}
                  {humanRequest && status === "interrupted" && (
                    <HumanRequestCard request={humanRequest} />
                  )}

                  {/* Streamed Output (Current Response) */}
                  {streamedContent && (
                    <div className="space-y-1">
                      <h4 className="text-[10px] font-medium text-muted-foreground/70 uppercase">Response</h4>
                      <div className="rounded-md px-3 py-2 bg-background border text-xs leading-relaxed max-h-[200px] overflow-y-auto">
                        <MessageContent content={streamedContent} />
                      </div>
                    </div>
                  )}

                  {/* Active Thoughts */}
                  {thoughts.length > 0 && (
                    <div className="space-y-1">
                      <h4 className="text-[10px] font-medium text-muted-foreground/70 uppercase">Thoughts</h4>
                      {thoughts.slice(-3).reverse().map(thought => (
                        <ThoughtCard key={thought.id} thought={thought} />
                      ))}
                    </div>
                  )}

                  {/* Task Pipeline */}
                  {tasks.length > 0 && (
                    <div className="space-y-1">
                      <h4 className="text-[10px] font-medium text-muted-foreground/70 uppercase">Action Plan</h4>
                      <div className="pl-1">
                        <TaskSteps tasks={tasks} />
                      </div>
                    </div>
                  )}

                  {/* Artifacts */}
                  {artifacts.length > 0 && (
                    <div className="space-y-1">
                      <h4 className="text-[10px] font-medium text-muted-foreground/70 uppercase">Artifacts</h4>
                      <ArtifactsList artifacts={artifacts} />
                    </div>
                  )}
                </div>
              </ScrollArea>
            )}
          </div>
        )}

        {/* BOTTOM ZONE: Static Context Tabs */}
        <Tabs
          value={activeTab}
          onValueChange={setActiveTab}
          className="flex-1 flex flex-col min-h-0"
        >
          <div className="px-1 pt-2 shrink-0 bg-background/95 backdrop-blur supports-[backdrop-filter]:bg-background/60">
            <TabsList className="flex flex-wrap h-auto w-full gap-1 bg-transparent justify-start">
              <TabsTrigger
                value="memory"
                title={t("chat.context.tabMemory")}
                className="flex-1 min-w-[2.5rem] px-2 py-1.5 text-xs"
              >
                <Brain className="h-3.5 w-3.5 mr-1" />
                <span className="hidden xl:inline">Memory</span>
              </TabsTrigger>
              <TabsTrigger
                value="plan"
                title={t("chat.context.tabPlan")}
                className="flex-1 min-w-[2.5rem] px-2 py-1.5 text-xs"
              >
                <MapIcon className="h-3.5 w-3.5 mr-1" />
                <span className="hidden xl:inline">Plan</span>
              </TabsTrigger>
              <TabsTrigger
                value="state"
                title={t("chat.context.tabState")}
                className="flex-1 min-w-[2.5rem] px-2 py-1.5 text-xs"
              >
                <Cpu className="h-3.5 w-3.5 mr-1" />
                <span className="hidden xl:inline">State</span>
              </TabsTrigger>
              <TabsTrigger
                value="tools"
                title="Tools"
                className="flex-1 min-w-[2.5rem] px-2 py-1.5 text-xs hidden sm:flex"
              >
                <Wrench className="h-3.5 w-3.5 mr-1" />
                <span className="hidden xl:inline">Tools</span>
              </TabsTrigger>
              <TabsTrigger
                value="knowledge"
                title={t("chat.context.tabKnowledge")}
                className="flex-1 min-w-[2.5rem] px-2 py-1.5 text-xs"
              >
                <Database className="h-3.5 w-3.5 mr-1" />
                <span className="hidden xl:inline">RAG</span>
              </TabsTrigger>
              <TabsTrigger
                value="resources"
                title={t("chat.context.tabResources")}
                className="flex-1 min-w-[2.5rem] px-2 py-1.5 text-xs"
              >
                <Layers className="h-3.5 w-3.5 mr-1" />
                <span className="hidden xl:inline">Files</span>
              </TabsTrigger>
            </TabsList>
          </div>

          <div className="flex-1 overflow-hidden relative">
            <TabsContent value="memory" className="h-full m-0">
              <MemoryTab projectId={projectId} />
            </TabsContent>

            <TabsContent value="plan" className="h-full m-0">
              <PlanTab activeThreadId={activeThreadId} />
            </TabsContent>

            <TabsContent value="state" className="h-full m-0">
              <StateTab activeThreadId={activeThreadId} />
            </TabsContent>

            <TabsContent value="tools" className="h-full m-0">
              <ToolsTab />
            </TabsContent>

            <TabsContent value="knowledge" className="h-full m-0">
              <KnowledgeTab projectId={projectId} />
            </TabsContent>

            <TabsContent value="resources" className="h-full m-0">
              <ResourcesTab projectId={projectId} />
            </TabsContent>
          </div>
        </Tabs>
      </div>
    )
  },
)

ContextPanel.displayName = "ContextPanel"

