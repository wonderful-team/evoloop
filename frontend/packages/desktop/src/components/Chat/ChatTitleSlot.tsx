import { Button } from "@evoloop/shared/components/ui/button"
import { cn } from "@evoloop/shared/lib/utils"
import { useQuery } from "@tanstack/react-query"
import {
  Home,
  Loader2,
  Maximize2,
  Minimize2,
  PanelLeft,
  PanelRight,
} from "lucide-react"
import { memo } from "react"
import { useTranslation } from "react-i18next"
import { PlanningService } from "@/client"
import { enterMiniWindow, exitMiniWindow } from "@/lib/miniWindow"
import { isTauri } from "@/lib/tauri"
import { useAgentStore } from "@/stores/agentStore"
import { useChatStore } from "@/stores/chatStore"
import { useProjectStore } from "@/stores/projectStore"
import { useUIStore } from "@/stores/uiStore"

/**
 * ChatTitleSlot — 聊天页在全局 AppTitleBar 中的上下文槽位。
 *
 * 仅在 /chat 且已选项目时由 AppTitleBar 挂载。
 * 所有 store 订阅内聚在此：流式更新只重渲染本组件，
 * 不会拖累全局标题栏。
 */

// ── 左侧：项目 > 目标/计划 > 运行步骤 ──────────────────────────
export const ChatTitleBreadcrumb = memo(function ChatTitleBreadcrumb() {
  const { t } = useTranslation()
  const currentProject = useProjectStore((s) => s.currentProject)
  const threadId = useChatStore((s) => s.threadId)
  const status = useAgentStore((s) => s.status)
  const agentState = useAgentStore((s) => s.agentState)

  // Fetch Plan
  const { data: planData } = useQuery({
    queryKey: ["threadPlan", threadId],
    queryFn: async () => {
      if (!threadId) return null
      return PlanningService.getPlan({ threadId })
    },
    enabled: !!threadId,
    staleTime: 5000,
  })

  // Use 'any' type casting to avoid strict type issues if types aren't fully synced
  // Assuming response structure: { plan: { title, steps: [...] }, ... }
  const typedPlan = planData as any
  const planTitle = typedPlan?.plan?.title
  const sessionGoal = useChatStore((s) => s.sessionGoal)
  const activeStep = typedPlan?.plan?.steps?.find(
    (s: any) => s.status === "in_progress",
  )

  // Decide what to show
  const displayTitle = planTitle || sessionGoal
  const isRunning = status === "running" || status === "summarizing"

  return (
    <div className="flex items-center text-xs text-muted-foreground min-w-0 overflow-hidden select-none">
      {/* Project */}
      <div className="flex items-center whitespace-nowrap hover:text-foreground transition-colors cursor-default min-w-0 shrink">
        <Home size={12} className="mr-1.5 opacity-70 shrink-0" />
        <span className="font-medium max-w-[120px] truncate min-w-0">
          {currentProject?.name}
        </span>
      </div>

      {/* Separator */}
      <span className="mx-2 opacity-50 shrink-0">›</span>

      {/* Plan / Goal */}
      {displayTitle ? (
        <div className="flex items-center whitespace-nowrap hover:text-foreground transition-colors cursor-default min-w-0 shrink">
          <span className="truncate max-w-[200px]" title={displayTitle}>
            {displayTitle}
          </span>
        </div>
      ) : (
        <span className="opacity-50 italic shrink-0">
          {t("chat.status.ready")}
        </span>
      )}

      {/* Active Step (Only if running or active plan) */}
      {(activeStep || isRunning) && (
        <>
          <span className="mx-2 opacity-50 shrink-0">›</span>
          <div className="flex items-center text-primary whitespace-nowrap min-w-0 shrink truncate animate-in fade-in slide-in-from-left-2">
            {isRunning && (
              <Loader2 size={10} className="mr-1.5 animate-spin shrink-0" />
            )}
            <span
              className="font-medium truncate min-w-0"
              title={activeStep?.description || agentState?.task_name}
            >
              {activeStep?.description ||
                agentState?.task_name ||
                (isRunning ? t("chat.status.working") : "")}
            </span>
          </div>
        </>
      )}
    </div>
  )
})

// ── 右侧：面板开关（常驻）+ 迷你模式 ──────────────────────────
export const ChatTitleActions = memo(function ChatTitleActions() {
  const { t } = useTranslation()
  const isCompactWindow = useUIStore((s) => s.isCompactWindow)
  const showContextPanel = useUIStore((s) => s.showContextPanel)
  const showChatListSheet = useUIStore((s) => s.showChatListSheet)
  const showChatList = useUIStore((s) => s.showChatList)
  const miniMode = useUIStore((s) => s.miniMode)
  const setShowChatListSheet = useUIStore((s) => s.setShowChatListSheet)
  const setShowContextPanel = useUIStore((s) => s.setShowContextPanel)
  const setShowChatList = useUIStore((s) => s.setShowChatList)
  const setMiniMode = useUIStore((s) => s.setMiniMode)

  const noDragStyle = { WebkitAppRegion: "no-drag" } as React.CSSProperties

  // 左侧面板：桌面端直接开合；窄窗走 Sheet
  const chatListActive = isCompactWindow ? showChatListSheet : showChatList
  const toggleChatList = () => {
    if (isCompactWindow) {
      setShowChatListSheet(!showChatListSheet)
    } else {
      setShowChatList(!showChatList)
    }
  }

  // 右侧面板：手动开合均持久化（与 ChatInterface 的自动展开语义协同）
  const contextActive = showContextPanel
  const toggleContext = () => {
    const next = !contextActive
    if (next) {
      localStorage.removeItem("chat.contextPanel.hidden")
    } else {
      localStorage.setItem("chat.contextPanel.hidden", "true")
    }
    setShowContextPanel(next)
  }

  const toggleMiniMode = async () => {
    const next = !miniMode
    if (isTauri()) {
      // 迷你模式 = 收缩窗口本身（置顶小窗）；失败则不切换状态
      const ok = next ? await enterMiniWindow() : await exitMiniWindow()
      if (!ok) return
    }
    setMiniMode(next)
  }

  return (
    <div className="flex items-center gap-0.5 shrink-0" style={noDragStyle}>
      <Button
        variant={chatListActive ? "secondary" : "ghost"}
        size="icon"
        className="h-7 w-7 text-muted-foreground"
        onClick={toggleChatList}
        title={t("common.openChatList")}
      >
        <PanelLeft className="h-4 w-4" />
      </Button>
      <Button
        variant={contextActive ? "secondary" : "ghost"}
        size="icon"
        className="h-7 w-7 text-muted-foreground"
        onClick={toggleContext}
        title={t("common.openContextPanel")}
      >
        <PanelRight className="h-4 w-4" />
      </Button>

      <div className="mx-1 h-3.5 w-px bg-border/60" />

      <Button
        variant={miniMode ? "default" : "ghost"}
        size="icon"
        className={cn(
          "h-7 w-7",
          miniMode
            ? "text-cta-foreground"
            : "text-muted-foreground hover:text-foreground",
        )}
        onClick={toggleMiniMode}
        title={t("common.miniMode")}
      >
        {miniMode ? (
          <Maximize2 className="h-4 w-4" />
        ) : (
          <Minimize2 className="h-4 w-4" />
        )}
      </Button>
    </div>
  )
})
