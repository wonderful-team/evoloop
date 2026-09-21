import { useCallback, useEffect, useMemo, useState } from "react"
import { motion } from "framer-motion"
import { useNavigate } from "@tanstack/react-router"
import { useChatStore } from "@/stores/chatStore"
import { useQuery, useQueryClient } from "@tanstack/react-query"
import {
  Inbox,
  Plus,
} from "lucide-react"
import { useTranslation } from "react-i18next"

import AutonomousDutyCanvasApp from "./canvas/AutonomousDutyCanvasApp"
import { adaptQueueTasksToDutyTasks } from "./core/taskAdapter"

import { OpenAPI } from "@/client/core/OpenAPI"
import { AgentService, SystemService } from "@/client"

import { Button } from "@evoloop/shared/components/ui/button"
import { ScrollArea } from "@evoloop/shared/components/ui/scroll-area"
import {
  Tabs,
  TabsContent,
  TabsList,
  TabsTrigger,
} from "@evoloop/shared/components/ui/tabs"
import {
  ResizableHandle,
  ResizablePanel,
  ResizablePanelGroup,
} from "@evoloop/shared/components/ui/resizable"

import { TaskRow } from "./queue/TaskRow"
import {
  TasksQueueApi,
  type QueueTask,
  type DashboardKpis,
} from "@/lib/tasksQueueApi"
import { DEMO } from "./core/demoData"
import { getDemoDashboard, getDemoTasks, setDemoRunning } from "./core/demoRuntime"
import { ExperimentNotice } from "./core/ExperimentNotice"
import { PulseWave } from "./queue/AgentPulse"
import { DutyRitualOverlay } from "./queue/DutyStartStopButton"
import { DutyHitlInputCard } from "./canvas/DutyHitlInputCard"
import { ProjectSwitcher } from "@/components/Sidebar/ProjectSwitcher"
import { useProjectStore } from "@/stores/projectStore"
import { ChatInputArea } from "@/components/Chat/ChatInputArea"
import { Bot, X } from "lucide-react"

const TABS: {
  key: string
  label: string
  statuses: string[]
  dotCls: string
  groups?: { label: string; statuses: string[]; dotCls: string }[]
}[] = [
  {
    key: "active",
    label: "进行时",
    statuses: ["in_progress", "pending"],
    dotCls: "bg-primary",
    groups: [
      { label: "进行中", statuses: ["in_progress"], dotCls: "bg-primary" },
      { label: "已挂起", statuses: ["__suspended__"], dotCls: "bg-amber-500" },
      { label: "待执行", statuses: ["pending"], dotCls: "bg-amber-500" },
    ],
  },
  { key: "proposed", label: "提案", statuses: ["proposed"], dotCls: "bg-violet-500" },
  { key: "waiting", label: "待验收", statuses: ["waiting_acceptance"], dotCls: "bg-sky-500" },
  {
    key: "done",
    label: "已结束",
    statuses: ["completed", "failed", "cancelled"],
    dotCls: "bg-emerald-500",
  },
]

export function AutonomousDutyPage() {
  const { t } = useTranslation()
  const qc = useQueryClient()
  const navigate = useNavigate()
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [activeTab, setActiveTab] = useState("active")
  const [ritual, setRitual] = useState<"start" | "stop" | null>(null)

  useEffect(() => {
    const handleRitual = (e: Event) => {
      const ph = (e as CustomEvent<{ phase: "start" | "stop" | "done" }>).detail?.phase
      setRitual(ph === "done" ? null : ph)
    }
    window.addEventListener("duty:ritual", handleRitual)
    return () => window.removeEventListener("duty:ritual", handleRitual)
  }, [])

  const [liveRun, setLiveRun] = useState<{ title: string; at: string } | null>(
    null,
  )
  const projectSwitcherOpen = useProjectStore(
    (state) => state.projectSwitcherOpen || undefined,
  )
  const projectId = useProjectStore(
    (state) => state.currentProject?.id ?? null,
  )
  const currentProject = useProjectStore((state) => state.currentProject ?? null)
  const scopedProjectId = projectId && projectId > 0 ? projectId : undefined

  // 项目切换时重置选中的任务
  useEffect(() => {
    setSelectedId(null)
  }, [projectId])

  const dash = useQuery<DashboardKpis>({
    queryKey: ["dutyDashboard", projectId ?? "global"],
    queryFn: () =>
      DEMO
        ? Promise.resolve(getDemoDashboard())
        : TasksQueueApi.dashboard(scopedProjectId),
  })

  const hitlPending = useQuery({
    queryKey: ["dutyHitl"],
    queryFn: () => TasksQueueApi.hitlPending(),
    // SSE 独驱：hitl_created/hitl_resolved 事件 → invalidate；连接建立/重连时
    // onopen 对账收敛断线窗口，不设周期轮询。
  })

  const queue = useQuery<{ items: QueueTask[]; count: number }>({
    queryKey: ["dutyQueue", projectId ?? "global"],
    queryFn: () =>
      DEMO
        ? Promise.resolve(getDemoTasks())
        : TasksQueueApi.list(undefined, scopedProjectId),
  })

  useEffect(() => {
    if (DEMO) return

    let disposed = false
    let source: EventSource | null = null

    async function connect() {
      const params = new URLSearchParams()
      if (scopedProjectId != null) params.set("project_id", String(scopedProjectId))
      try {
        const token =
          typeof OpenAPI.TOKEN === "function"
            ? await (OpenAPI.TOKEN as unknown as () => Promise<string>)()
            : OpenAPI.TOKEN
        if (token) params.set("token", token)
      } catch {
        // Cookie auth remains valid; EventSource cannot set Authorization headers.
      }
      if (disposed) return

      const query = params.toString()
      source = new EventSource(
        `${OpenAPI.BASE}/api/v1/stream/tasks${query ? `?${query}` : ""}`,
        { withCredentials: true },
      )
      // 连接建立/每次重连 → 对账一次：事件是加速器，状态以服务端为准，
      // 断线窗口内漏掉的事件由本次 refetch 收敛（不再用周期轮询兜底）。
      source.onopen = () => {
        void qc.invalidateQueries({ queryKey: ["dutyHitl"] })
        void qc.invalidateQueries({ queryKey: ["dutyQueue"] })
        void qc.invalidateQueries({ queryKey: ["dutyDashboard"] })
      }
      source.addEventListener("task_queue_updated", (ev) => {
        try {
          const payload = JSON.parse((ev as MessageEvent).data) as {
            event?: string
            title?: string | null
            status?: string
            at?: string
            tokens?: number
            thread_id?: string
          }
          if (payload.event === "task_taken") {
            setLiveRun({
              title: payload.title ?? "",
              at: payload.at ?? new Date().toISOString(),
            })
          } else if (
            payload.event === "task_updated" &&
            ["completed", "failed", "cancelled"].includes(
              payload.status ?? "",
            )
          ) {
            setLiveRun(null)
          }
          if (
            payload.event === "hitl_resolved" ||
            payload.event === "hitl_created"
          ) {
            void qc.invalidateQueries({ queryKey: ["dutyHitl"] })
          }
          
        } catch {
          /* payload optional */
        }
        void qc.invalidateQueries({ queryKey: ["dutyQueue"] })
        void qc.invalidateQueries({ queryKey: ["dutyDashboard"] })
        void qc.invalidateQueries({ queryKey: ["dutyPlan"] })
        void qc.invalidateQueries({ queryKey: ["dutyExec"] })
      })
    }

    void connect()
    return () => {
      disposed = true
      source?.close()
    }
  }, [DEMO, qc, scopedProjectId])

  const allTasks = useMemo(() => queue.data?.items ?? [], [queue.data])
  const dutyTasks = useMemo(() => {
    if (!allTasks || allTasks.length === 0) return undefined
    return adaptQueueTasksToDutyTasks(allTasks, hitlPending.data?.items)
  }, [allTasks, hitlPending.data?.items])
  const activeTabDef = TABS.find((x) => x.key === activeTab) ?? TABS[0]
  const tasks = useMemo(
    () => allTasks.filter((t) => activeTabDef.statuses.includes(t.status)),
    [allTasks, activeTabDef],
  )

  const handleTaskSelectFromCanvas = useCallback(
    (id: string | null) => {
      setSelectedId(id)
      if (!id) return
      const task = allTasks.find((t) => t.id === id)
      if (task) {
        const targetTab = TABS.find((tab) => tab.statuses.includes(task.status))
        if (targetTab && targetTab.key !== activeTab) {
          setActiveTab(targetTab.key)
        }
        const targetScrollId =
          activeTab === "active" && task.parent_id ? task.parent_id : id
        setTimeout(() => {
          const el = document.getElementById(`duty-task-row-${targetScrollId}`)
          el?.scrollIntoView({ behavior: "smooth", block: "nearest" })
        }, 80)
      }
    },
    [allTasks, activeTab],
  )

  const projects = useProjectStore((st) => st.projects)
  const storeLoading = useProjectStore((st) => st.isLoading)
  useEffect(() => {
    setSelectedId(null)
  }, [projectId])

  // blocked-chain detection: pending tasks whose dependencies contain a failed task
  const blockedInfo = useMemo(() => {
    const failedIds = new Set(
      allTasks.filter((t) => t.status === "failed").map((t) => t.id),
    )
    if (failedIds.size === 0) return null
    const blocked = allTasks.filter((t) => {
      if (t.status !== "pending") return false
      const deps = t.dependencies ?? []
      return deps.some((d) => failedIds.has(d))
    })
    if (blocked.length === 0) return null
    const blockerId = blocked[0]
      ? (blocked[0].dependencies ?? []).find((d) => failedIds.has(d))
      : undefined
    const blocker = blockerId
      ? allTasks.find((t) => t.id === blockerId)
      : null
    return {
      blocker: blocker?.title ?? "上游任务",
      blockerId: blocker?.id ?? "",
      count: blocked.length,
    }
  }, [allTasks])

  async function invalidate() {
    await qc.invalidateQueries({ queryKey: ["dutyQueue"] })
    await qc.invalidateQueries({ queryKey: ["dutyDashboard"] })
  }

  const handleToggleDuty = async () => {
    const current = dash.data?.duty_enabled === true
    const next = !current
    setRitual(next ? "start" : "stop")
    try {
      if (DEMO) {
        setDemoRunning(next)
      } else {
        await SystemService.updateCustomerServiceDuty({
          requestBody: { enabled: next, channels: [] },
        })
      }
      setTimeout(() => setRitual(null), next ? 1500 : 900)
      await invalidate()
    } catch (e) {
      console.error("Failed to toggle duty:", e)
    }
  }

  const storeReady = !storeLoading || projects.length > 0

  return (
    <div className="h-full flex flex-col relative bg-background overflow-hidden subpixel-antialiased [transform:none]">
      <ExperimentNotice />
      {!storeReady && (
        <div className="absolute inset-0 z-30 flex items-center justify-center bg-background/60 backdrop-blur-xs">
          <div className="text-xs text-muted-foreground animate-pulse">
            正在恢复工作空间…
          </div>
        </div>
      )}
      <div className="flex-1 min-h-0 w-full overflow-hidden relative">
        <ResizablePanelGroup
          direction="horizontal"
          className="h-full w-full min-w-0 overflow-hidden"
        >
          {/* Left: 任务面板 (占比约 23%，紧凑适中，支持自由拖动调节) */}
          <ResizablePanel
            id="duty-tasks-panel"
            order={1}
            defaultSize={23}
            minSize={15}
            maxSize={45}
            className="min-w-[220px] overflow-hidden"
          >
            <div className="flex flex-col h-full w-full min-w-0 bg-sidebar border-r border-border/80 overflow-hidden">
        <div className="p-2 shrink-0 w-full min-w-0 overflow-hidden">
          <ProjectSwitcher
            open={projectSwitcherOpen}
            onOpenChange={(value) => {
              if (!value) useProjectStore.getState().closeProjectSwitcher()
            }}
          />
        </div>
        {/* Live status strip (SSE-driven) */}
        <div className="px-2 pb-1 shrink-0">
          <div className="rounded-md bg-muted/40 border border-border/40 px-2.5 py-1.5 flex items-center gap-2">
            <span
              className={`inline-block h-1.5 w-1.5 rounded-full shrink-0 ${
                liveRun ? "bg-primary animate-pulse" : "bg-emerald-500/60"
              }`}
            />
            {hitlPending.data && hitlPending.data.count > 0 ? (
              <button
                className="text-[11px] truncate text-left"
                onClick={() =>
                  (hitlPending.data?.items ?? [])[0]?.task_id &&
                  setSelectedId((hitlPending.data?.items ?? [])[0].task_id)
                }
              >
                <span className="text-amber-600 dark:text-amber-400 font-medium">
                  ⚠ {hitlPending.data.count} 项审批等待你
                </span>
                <span className="text-muted-foreground ml-1">
                  点击查看 · 也可在工作流执行流中处理
                </span>
              </button>
            ) : liveRun ? (
              <span className="text-[11px] truncate">
                <span className="text-primary font-medium">正在执行</span>
                <span className="text-foreground font-medium ml-1">
                  {liveRun.title}
                </span>
              </span>
            ) : blockedInfo ? (
              <span className="text-[11px] truncate">
                <span className="text-destructive font-medium">
                  ⚠ 队列阻塞
                </span>
                <span className="text-foreground ml-1">
                  {blockedInfo.blocker} 失败，{blockedInfo.count} 条任务被阻塞
                </span>
                <button
                  className="text-primary ml-1.5 hover:underline"
                  onClick={async () => {
                    await TasksQueueApi.rerun(blockedInfo.blockerId).catch(
                      () => null,
                    )
                    await invalidate()
                  }}
                >
                  重跑
                </button>
              </span>
            ) : allTasks.length === 0 ? (
              <span className="text-[11px] text-muted-foreground truncate">
                还没有任务 · 点左下角「新建任务」开始，或开启值守让 Agent 自主工作
              </span>
            ) : (
              <span className="text-[11px] text-muted-foreground truncate">
                值守空闲 · 队列 {allTasks.filter((t) => t.status === "pending").length} 条待执行
              </span>
            )}
            <span className="flex-1" />
          </div>
        </div>
        <Tabs
          value={activeTab}
          onValueChange={setActiveTab}
          className="flex flex-col flex-1 min-h-0 min-w-0 w-full overflow-hidden"
        >
          <div className="p-2 pt-0 shrink-0 w-full">
            <TabsList className="w-full grid grid-cols-4">
              {TABS.map((tab) => {
                const count = allTasks.filter((item) =>
                  tab.statuses.includes(item.status),
                ).length
                return (
                  <TabsTrigger key={tab.key} value={tab.key} className="text-xs">
                    {tab.label}
                    <span className="font-mono text-[10px] opacity-70">
                      {count}
                    </span>
                  </TabsTrigger>
                )
              })}
            </TabsList>
          </div>
          <TabsContent
            value={activeTabDef.key}
            className="flex-1 flex flex-col min-h-0 mt-0 data-[state=inactive]:hidden"
          >
          <ScrollArea className="flex-1">
          <div
            key={activeTab}
            className="pl-1 pr-2.5 py-1.5 space-y-3 animate-in fade-in slide-in-from-bottom-1 duration-200"
          >
              {activeTabDef.groups
                ? activeTabDef.groups.map((g) => {
                    const suspendedIds = new Set(
                      (hitlPending.data?.items ?? [])
                        .map((h) => h.task_id)
                        .filter(Boolean) as string[],
                    )
                    const items = allTasks.filter((t) => {
                      // 任务面板的“进行时”中只显示主干根任务（无 parent_id 且无前置依赖）
                      const isRoot =
                        !t.parent_id && (!t.dependencies || t.dependencies.length === 0)
                      if (!isRoot) return false

                      if (g.statuses[0] === "__suspended__") {
                        // 已挂起组：进行中且有 pending 审批的任务
                        return (
                          t.status === "in_progress" && suspendedIds.has(t.id)
                        )
                      }
                      if (g.statuses.includes("in_progress")) {
                        // 进行中组：排除已挂起的
                        return (
                          t.status === "in_progress" &&
                          !suspendedIds.has(t.id)
                        )
                      }
                      return g.statuses.includes(t.status)
                    })
                    if (items.length === 0) return null
                    return (
                      <div key={g.label} className="space-y-2">
                        <div className="flex items-center gap-1.5 px-0.5 text-[11px] font-medium text-muted-foreground">
                          <span
                            className={`inline-block h-1 w-1 rounded-full ${g.dotCls}`}
                          />
                          {g.label}
                          <span className="font-mono text-[10px] opacity-70">
                            {items.length}
                          </span>
                        </div>
                        {items.map((t) => (
                          <motion.div
                            key={t.id}
                            initial={{ opacity: 0, y: 6 }}
                            animate={{ opacity: 1, y: 0, transitionEnd: { transform: "none" } }}
                            transition={{ duration: 0.2 }}
                          >
                            <TaskRow
                              task={t}
                              suspended={g.statuses[0] === "__suspended__"}
                              selected={t.id === selectedId}
                              onSelect={() => setSelectedId(t.id)}
                              onDoubleClick={() => {
                                window.dispatchEvent(
                                  new CustomEvent("canvas:advance-task-state", {
                                    detail: { taskId: t.id },
                                  }),
                                )
                              }}
                              showProject={!scopedProjectId}
                              projectName={
                                projects?.find(
                                  (pr) => pr.id === t.project_id,
                                )?.project_name
                              }
                            />
                          </motion.div>
                        ))}
                      </div>
                    )
                  })
                : tasks.map((t) => (
                    <motion.div
                      key={t.id}
                      initial={{ opacity: 0, y: 6 }}
                      animate={{ opacity: 1, y: 0, transitionEnd: { transform: "none" } }}
                      transition={{ duration: 0.2 }}
                    >
                      <TaskRow
                        task={t}
                        selected={t.id === selectedId}
                        onSelect={() => setSelectedId(t.id)}
                        onDoubleClick={() => {
                          window.dispatchEvent(
                            new CustomEvent("canvas:advance-task-state", {
                              detail: { taskId: t.id },
                            }),
                          )
                        }}
                        showProject={!scopedProjectId}
                        projectName={
                          projects?.find((pr) => pr.id === t.project_id)
                            ?.project_name
                        }
                      />
                    </motion.div>
                  ))}
            {tasks.length === 0 && !queue.isLoading && (
              <div className="text-center text-xs text-muted-foreground py-12 space-y-1.5">
                <Inbox className="h-6 w-6 mx-auto opacity-40" />
                <p>{t("dutyBoard.empty")}</p>
              </div>
            )}
          </div>
          </ScrollArea>
          </TabsContent>
        </Tabs>
        <div className="shrink-0 p-2.5 border-t border-border/50">
          <Button
            variant="outline"
            className="w-full gap-1.5 h-8 text-xs bg-muted/40 hover:bg-muted/70 border-border/60 transition-colors"
            onClick={() => {
              useChatStore
                .getState()
                .setPendingTaskDraft(
                  "请帮我把这件事建成值守任务：\n· 要做的事：\n· 执行频率（可选，如每天 09:00 / 每 30 分钟）：\n· 需要特别注意的风险点（可选）：",
                )
              navigate({ to: "/chat" })
            }}
            title={t("dutyBoard.createHint")}
          >
            <Plus className="h-3.5 w-3.5" />
            {t("dutyBoard.create")}
          </Button>
        </div>
      </div>
    </ResizablePanel>

          {/* 拖动手柄 (ResizableHandle) */}
          <ResizableHandle
            withHandle
            className="w-1.5 -mx-0.5 bg-transparent hover:bg-primary/20 active:bg-primary/30 transition-colors z-20 [&>div]:bg-border/60 [&>div]:hover:bg-primary"
          />

          {/* Right: 无限画布工作台 (占比约 77%) */}
          <ResizablePanel
            id="duty-canvas-panel"
            order={2}
            defaultSize={77}
            minSize={30}
            className="min-w-0 overflow-hidden"
          >
            <div className="flex flex-col h-full w-full min-w-0 bg-background relative overflow-hidden">

        <AutonomousDutyCanvasApp
          key={projectId ?? "global"}
          tasks={dutyTasks}
          isLoading={queue.isLoading}
          hideSidebar={true}
          hideTopBar={true}
          dutyEnabled={dash.data?.duty_enabled === true}
          onToggleDuty={handleToggleDuty}
          externalSelectedTaskId={selectedId}
          highlightStatuses={activeTabDef.statuses}
          onTaskSelect={handleTaskSelectFromCanvas}
          onApproveTask={async (taskId) => {
            try {
              await TasksQueueApi.accept(taskId)
              await invalidate()
            } catch (err) {
              console.error("Failed to accept task:", err)
            }
          }}
          onRejectTask={async (taskId, feedback) => {
            try {
              await TasksQueueApi.reject(taskId, feedback)
              await invalidate()
            } catch (err) {
              console.error("Failed to reject task:", err)
            }
          }}
          onConfirmProposalTask={async (taskId) => {
            try {
              await TasksQueueApi.confirm(taskId)
              await invalidate()
            } catch (err) {
              console.error("Failed to confirm proposal:", err)
            }
          }}
          onRerunTask={async (taskId) => {
            try {
              await TasksQueueApi.rerun(taskId)
              await invalidate()
            } catch (err) {
              console.error("Failed to rerun task:", err)
            }
          }}
          onConfirmHitl={async (taskId, grantMode) => {
            const task = dutyTasks?.find((t) => t.id === taskId)
            const threadId =
              task?.lastThreadId ||
              (task?.rawQueueTask as { origin_thread_id?: string })?.origin_thread_id
            if (threadId) {
              try {
                await AgentService.resumeChat({
                  requestBody: {
                    thread_id: threadId,
                    user_input: "approve",
                    grant_mode: grantMode ?? "once",
                  },
                })
                await invalidate()
                void qc.invalidateQueries({ queryKey: ["dutyHitl"] })
              } catch (err) {
                console.error("Failed to approve HITL via AgentService:", err)
              }
            }
          }}
          onCancelHitl={async (taskId) => {
            const task = dutyTasks?.find((t) => t.id === taskId)
            const threadId =
              task?.lastThreadId ||
              (task?.rawQueueTask as { origin_thread_id?: string })?.origin_thread_id
            if (threadId) {
              try {
                await AgentService.resumeChat({
                  requestBody: {
                    thread_id: threadId,
                    user_input: "cancel",
                    grant_mode: "once",
                  },
                })
                await invalidate()
                void qc.invalidateQueries({ queryKey: ["dutyHitl"] })
              } catch (err) {
                console.error("Failed to cancel HITL via AgentService:", err)
              }
            }
          }}
          renderInputBar={({ selectedTask, selectedTaskIds, isMultiSelected, onClearSelection }) => {
            const pendingItems = hitlPending.data?.items ?? []
            // 🌟 严格限定：仅在用户明确点选了处于待决策/待授权状态的节点时，才对位替换底部输入框为审批卡片
            // 未选节点（全局模式）或选中的节点无 HITL 时，绝对不劫持正常的 Prompt 输入框
            const activeHitl = selectedTask
              ? pendingItems.find(
                  (h) =>
                    h.task_id === selectedTask.id ||
                    (selectedTask.lastThreadId && h.thread_id === selectedTask.lastThreadId),
                ) ||
                (selectedTask.status === "confirm" ||
                selectedTask.hitl?.pending ||
                selectedTask.humanRequest?.status === "pending"
                  ? {
                      request_id:
                        selectedTask.humanRequest?.requestId ||
                        selectedTask.hitl?.requestId ||
                        selectedTask.id,
                      thread_id: selectedTask.lastThreadId || "",
                      type:
                        selectedTask.humanRequest?.type ||
                        selectedTask.hitl?.action ||
                        "confirmation",
                      description:
                        selectedTask.humanRequest?.prompt ||
                        selectedTask.humanRequest?.description ||
                        selectedTask.hitl?.description ||
                        "需要您对本任务进行确认授权",
                      context: selectedTask.humanRequest?.context || null,
                      options: selectedTask.humanRequest?.options || [],
                      task_id: selectedTask.id,
                      task_title: selectedTask.title,
                      task_no: selectedTask.taskNo,
                    }
                  : null)
              : null

            // 🌟 当选中的当前节点遇到待审批的 HITL 项时，完全对齐 /chat 心智：自动隐藏输入框，替换为精致决策卡片
            if (activeHitl) {
              return (
                <DutyHitlInputCard
                  hitl={activeHitl}
                  onClose={onClearSelection}
                  onResolved={async () => {
                    await invalidate()
                  }}
                />
              )
            }

            return (
              <ChatInputArea
              className="p-0"
              cardClassName="bg-[var(--panel,#ffffff)] dark:bg-[#15161b] shadow-md border-border/80"
              currentProject={currentProject}
              isGlobalMode={!currentProject}
              hideTerminal={true}
              hideVoice={true}
              hideAutoSpeak={true}
              hideRecording={true}
              contextSlot={
                selectedTask ? (
                  <div className="inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-xs font-medium bg-primary/10 text-primary border border-primary/20 select-none max-w-[380px]">
                    <Bot className="h-3.5 w-3.5 shrink-0" />
                    <span className="truncate">
                      #T-{selectedTask.taskNo} {selectedTask.title}
                    </span>
                    <button
                      type="button"
                      onClick={onClearSelection}
                      className="hover:opacity-70 ml-0.5 cursor-pointer"
                      title="退出节点对话，返回全局值守"
                    >
                      <X className="h-3 w-3" />
                    </button>
                  </div>
                ) : isMultiSelected ? (
                  <div className="inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-xs font-medium bg-primary/10 text-primary border border-primary/20 select-none">
                    <Bot className="h-3.5 w-3.5 shrink-0" />
                    <span>已多选 {selectedTaskIds.size} 个任务</span>
                    <button
                      type="button"
                      onClick={onClearSelection}
                      className="hover:opacity-70 ml-0.5 cursor-pointer"
                      title="取消多选"
                    >
                      <X className="h-3 w-3" />
                    </button>
                  </div>
                ) : null
              }
              onSend={(text, files) => {
                if (selectedTask) {
                  // 1. 本地画布动画更新
                  window.dispatchEvent(
                    new CustomEvent("canvas:node-chat", {
                      detail: { taskId: selectedTask.id, message: text, files },
                    }),
                  )
                  // 2. 若任务具有已激活的对话线程，向后端真实提交消息
                  if (selectedTask.lastThreadId) {
                    useChatStore.getState().setThread(selectedTask.lastThreadId, null)
                    useChatStore.getState().sendMessage(text).catch((err: unknown) => {
                      console.warn("Failed to send message:", err)
                    })
                  }
                } else {
                  // 1. 本地画布飞镜与临时节点插入动画
                  window.dispatchEvent(
                    new CustomEvent("canvas:global-prompt", {
                      detail: { text, files },
                    }),
                  )
                  // 2. 向后端任务队列持久化真实新建任务！
                  const pId = scopedProjectId ?? 0
                  const firstLine = text.trim().split("\n")[0] || ""
                  const title = firstLine.slice(0, 30) || "值守新任务"
                  TasksQueueApi.create({
                    title,
                    description: text,
                    project_id: pId,
                    type: "once",
                    priority: "medium",
                  })
                    .then(async () => {
                      await invalidate()
                    })
                    .catch((err) => {
                      console.error("Failed to create task in backend:", err)
                    })
                }
              }}
              onStop={() => {}}
              isAgentWorking={false}
              isSending={false}
              isStopPending={false}
            />
          )
        }}
        />
            </div>
          </ResizablePanel>
        </ResizablePanelGroup>
      </div>

      {/* ── 底部：整页 KITT 往返扫描 ── */}
      <PulseWave active={dash.data?.duty_enabled === true} />

      {/* 值守启停转场仪式遮罩 */}
      {ritual && <DutyRitualOverlay phase={ritual} />}
    </div>
  )
}
