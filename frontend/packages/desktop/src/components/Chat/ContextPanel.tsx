import {
  Activity,
  Brain,
  Database,
  Globe,
  LayoutDashboard,
  Loader2,
  X,
} from "lucide-react"
import { memo, useState, useEffect } from "react"
import { useTranslation } from "react-i18next"
import { Button } from "@evoloop/shared/components/ui/button"
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@evoloop/shared/components/ui/tabs"
import { ActivityTab } from "./context/ActivityTab"
import { ContextGroupTab } from "./context/ContextGroupTab"
import { useChatStore } from "@/stores/chatStore"

interface ContextPanelProps {
  projectId?: number
  activeThreadId?: string
  autoSwitchToTab?: string
  onClose?: () => void
  isGlobalMode?: boolean
}

/**
 * Agent Workstation — Right sidebar panel.
 * Two tabs: Activity (runtime) and Context (project assets).
 */
export const ContextPanel = memo(
  ({ projectId, activeThreadId, autoSwitchToTab, onClose, isGlobalMode }: ContextPanelProps) => {
    const { t } = useTranslation()
    const [activeTab, setActiveTab] = useState("activity")

    const status = useChatStore((s) => s.status)
    const isAgentActive = status === "running" || status === "interrupted" || status === "summarizing"

    // Auto-switch tab based on context
    useEffect(() => {
      if (autoSwitchToTab) {
        if (["memory", "knowledge", "resources"].includes(autoSwitchToTab)) {
          setActiveTab("context")
        } else if (["plan", "state", "tools"].includes(autoSwitchToTab)) {
          setActiveTab("activity")
        } else if (autoSwitchToTab === "changes") {
          // Handled by ChatInterface sidebar
        } else {
          setActiveTab(autoSwitchToTab)
        }
      }
    }, [autoSwitchToTab])

    // Auto-switch to activity tab when running
    useEffect(() => {
      if (status === "running") {
        setActiveTab("activity")
      }
    }, [status])


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
        {/* Header */}
        <div className="flex items-center justify-between p-3 border-b h-14 shrink-0">
          <span className="font-semibold text-sm flex items-center gap-2">
            {isAgentActive ? (
              <Loader2 className="h-4 w-4 text-primary animate-spin" />
            ) : (
              <LayoutDashboard className="h-4 w-4 text-muted-foreground" />
            )}
            {t("chat.context.title")}
          </span>
          {onClose && (
            <Button variant="ghost" size="icon" className="h-7 w-7" onClick={onClose}>
              <X className="h-4 w-4" />
            </Button>
          )}
        </div>

        {/* Two tabs */}
        <Tabs
          value={activeTab}
          onValueChange={setActiveTab}
          className="flex-1 flex flex-col min-h-0"
        >
          <div className="p-2 border-b bg-muted/10 shrink-0">
            <TabsList className="w-full grid grid-cols-2">
              <TabsTrigger value="activity" className="text-xs">
                <Activity className="h-3.5 w-3.5 mr-1.5" />
                {t("chat.context.tabActivity")}
              </TabsTrigger>
              <TabsTrigger value="context" className="text-xs">
                <Database className="h-3.5 w-3.5 mr-1.5" />
                {t("chat.context.groupContext")}
              </TabsTrigger>
            </TabsList>
          </div>

          <div className="flex-1 overflow-hidden relative">
            <TabsContent value="activity" className="h-full m-0 data-[state=inactive]:hidden">
              <ActivityTab activeThreadId={activeThreadId} />
            </TabsContent>

            <TabsContent value="context" className="h-full m-0 data-[state=inactive]:hidden">
              <ContextGroupTab projectId={projectId} />
            </TabsContent>
          </div>
        </Tabs>
      </div>
    )
  },
)

ContextPanel.displayName = "ContextPanel"
