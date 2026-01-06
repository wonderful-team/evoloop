import {
  Brain,
  Cpu,
  Database,
  Layers,
  Map as MapIcon,
  Wrench,
  X,
} from "lucide-react"
import { memo, useState } from "react"
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

interface ContextPanelProps {
  projectId?: number
  activeThreadId?: string
  onClose?: () => void
}

export const ContextPanel = memo(
  ({ projectId, activeThreadId, onClose }: ContextPanelProps) => {
    const { t } = useTranslation()
    const [activeTab, setActiveTab] = useState("memory")

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
        <div className="flex items-center justify-between p-3 border-b h-14 shrink-0">
          <span className="font-semibold text-sm flex items-center gap-2">
            <Brain className="h-4 w-4 text-primary" />
            {t("chat.context.title")}
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

        <Tabs
          value={activeTab}
          onValueChange={setActiveTab}
          className="flex-1 flex flex-col min-h-0"
        >
          <div className="px-1 pt-2 shrink-0">
            <TabsList className="flex flex-wrap h-auto w-full gap-1 bg-transparent justify-start">
              <TabsTrigger
                value="memory"
                title={t("chat.context.tabMemory")}
                className="flex-1 min-w-[3rem] px-2 py-1.5"
              >
                <Brain className="h-4 w-4" />
              </TabsTrigger>
              <TabsTrigger
                value="plan"
                title={t("chat.context.tabPlan")}
                className="flex-1 min-w-[3rem] px-2 py-1.5"
              >
                <MapIcon className="h-4 w-4" />
              </TabsTrigger>
              <TabsTrigger
                value="state"
                title={t("chat.context.tabState")}
                className="flex-1 min-w-[3rem] px-2 py-1.5"
              >
                <Cpu className="h-4 w-4" />
              </TabsTrigger>
              <TabsTrigger
                value="tools"
                title="Tools"
                className="flex-1 min-w-[3rem] px-2 py-1.5"
              >
                <Wrench className="h-4 w-4" />
              </TabsTrigger>
              <TabsTrigger
                value="knowledge"
                title={t("chat.context.tabKnowledge")}
                className="flex-1 min-w-[3rem] px-2 py-1.5"
              >
                <Database className="h-4 w-4" />
              </TabsTrigger>
              <TabsTrigger
                value="resources"
                title={t("chat.context.tabResources")}
                className="flex-1 min-w-[3rem] px-2 py-1.5"
              >
                <Layers className="h-4 w-4" />
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
