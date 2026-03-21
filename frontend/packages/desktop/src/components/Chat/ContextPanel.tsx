import {
  Brain,
  Cpu,
  Database,
  Globe,
  LayoutDashboard,
  Loader2,
  Map as MapIcon,
  X,
} from "lucide-react"
import { memo, useState, useEffect } from "react"
import { useTranslation } from "react-i18next"
import { Button } from "@evoloop/shared/components/ui/button"
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@evoloop/shared/components/ui/tabs"
// Import Tab Components
import { PlanTab } from "./context/PlanTab"
import { ContextGroupTab } from "./context/ContextGroupTab"
import { SystemGroupTab } from "./context/SystemGroupTab"

// Import Agent Features
import { useChatStore } from "@/stores/chatStore"

interface ContextPanelProps {
  projectId?: number
  activeThreadId?: string
  autoSwitchToTab?: string
  onClose?: () => void
  isGlobalMode?: boolean
}

/**
 * AgentWorkstation (formerly ContextPanel)
 * Dashboard for Project Context, Plans, and System State.
 */
export const ContextPanel = memo(
  ({ projectId, activeThreadId, autoSwitchToTab, onClose, isGlobalMode }: ContextPanelProps) => {
    const { t } = useTranslation()
    const [activeTab, setActiveTab] = useState("context")

    // --- Store Selectors ---
    const status = useChatStore((s) => s.status)

    // Determine if Agent is active
    const isAgentActive = status === "running" || status === "interrupted" || status === "summarizing"

    // Auto-switch Tab based on context
    useEffect(() => {
      if (autoSwitchToTab) {
        // Map old tab names to new groups if needed, or assume backend sends group name?
        // Assuming autoSwitch might send 'plan'.
        // If it sends 'memory'/'knowledge', map to 'context'.
        if (["memory", "knowledge", "resources"].includes(autoSwitchToTab)) {
          setActiveTab("context")
        } else if (["state", "tools"].includes(autoSwitchToTab)) {
          setActiveTab("system")
        } else if (autoSwitchToTab === "changes") {
          // No longer in ContextPanel, maybe handled by ChatInterface to open sidebar?
          // For now, avoid crashing.
        } else {
          setActiveTab(autoSwitchToTab)
        }
      }
    }, [autoSwitchToTab])

    // Default to 'context' if no auto-switch
    useEffect(() => {
      if (!autoSwitchToTab) {
        setActiveTab("context") // Primary view
      }
    }, [autoSwitchToTab])

    // Global mode - show simplified context panel
    if (isGlobalMode) {
      return (
        <div className="flex flex-col h-full bg-background">
          {/* Header */}
          <div className="flex items-center justify-between p-3 border-b h-14 shrink-0">
            <span className="font-semibold text-sm flex items-center gap-2">
              <Globe className="h-4 w-4 text-blue-500" />
              {t("chat.context.globalTitle", "全局模式")}
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

          {/* Global Mode Info */}
          <div className="flex-1 flex flex-col items-center justify-center p-6 text-center">
            <div className="w-16 h-16 rounded-full bg-gradient-to-br from-blue-500 to-purple-500 flex items-center justify-center mb-4">
              <Globe className="h-8 w-8 text-white" />
            </div>
            <h3 className="font-semibold text-lg mb-2">
              {t("chat.context.globalTitle", "全局模式")}
            </h3>
            <p className="text-sm text-muted-foreground max-w-[200px]">
              {t("chat.context.globalDesc", "您正在进行跨项目对话。代码上下文和文件操作在此模式下不可用。")}
            </p>
          </div>
        </div>
      )
    }

    if (typeof projectId !== "number" || Number.isNaN(projectId)) {
      return (
        <div className="flex flex-col items-center justify-center h-full text-muted-foreground p-4 text-center">
          <Brain className="h-10 w-10 mb-2 opacity-20" />
          <p>{t("chat.context.selectProject")}</p>
        </div>
      )
    }

    return (
      <div className="flex flex-col h-full bg-background">
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

        {/* STATIC CONTEXT TABS (Full Height) */}
        <Tabs
          value={activeTab}
          onValueChange={setActiveTab}
          className="flex-1 flex flex-col min-h-0"
        >
          <div className="p-2 border-b bg-muted/10 shrink-0">
            <TabsList className="w-full grid grid-cols-3">
              <TabsTrigger value="context" className="text-xs">
                <Database className="h-3.5 w-3.5 mr-1.5" />
                {t("chat.context.groupContext", "Context")}
              </TabsTrigger>
              <TabsTrigger value="plan" className="text-xs">
                <MapIcon className="h-3.5 w-3.5 mr-1.5" />
                {t("chat.context.tabPlan", "Plan")}
              </TabsTrigger>
              <TabsTrigger value="system" className="text-xs">
                <Cpu className="h-3.5 w-3.5 mr-1.5" />
                {t("chat.context.groupSystem", "System")}
              </TabsTrigger>
            </TabsList>
          </div>

          <div className="flex-1 overflow-hidden relative">
            <TabsContent value="context" className="h-full m-0 data-[state=inactive]:hidden">
              <ContextGroupTab projectId={projectId} />
            </TabsContent>

            <TabsContent value="plan" className="h-full m-0 data-[state=inactive]:hidden">
              <PlanTab activeThreadId={activeThreadId} />
            </TabsContent>

            <TabsContent value="system" className="h-full m-0 data-[state=inactive]:hidden">
              <SystemGroupTab activeThreadId={activeThreadId} />
            </TabsContent>
          </div>
        </Tabs>
      </div>
    )
  },
)

ContextPanel.displayName = "ContextPanel"

