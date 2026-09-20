import { useEffect, useMemo, useState } from "react"
import { motion } from "framer-motion"
import { useNavigate } from "@tanstack/react-router"
import { useChatStore } from "@/stores/chatStore"
import { useQuery, useQueryClient } from "@tanstack/react-query"
import {
  Inbox,
  Plus,
} from "lucide-react"
import { useTranslation } from "react-i18next"

import AutonomousDutyCanvasApp from "../v2/AutonomousDutyCanvasApp"

import { OpenAPI } from "@/client/core/OpenAPI"

import { Button } from "@evoloop/shared/components/ui/button"
import { ScrollArea } from "@evoloop/shared/components/ui/scroll-area"
import {
  Tabs,
  TabsContent,
  TabsList,
  TabsTrigger,
} from "@evoloop/shared/components/ui/tabs"

import { TaskRow } from "./TaskRow"
import {
  TasksQueueApi,
  type QueueTask,
  type DashboardKpis,
} from "@/lib/tasksQueueApi"
import { DEMO } from "./demoData"
import { getDemoDashboard, getDemoTasks } from "./demoRuntime"
import { ExperimentNotice } from "./ExperimentNotice"
import { PulseWave } from "./AgentPulse"
import {
  DutyRitualOverlay,
  DutyStartStopButton,
} from "./DutyStartStopButton"
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
    // 主推送走 SSE（hitl_created / hitl_resolved）；60s 仅兜底断线漏事件
    refetchInterval: 60000,
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
  const activeTabDef = TABS.find((x) => x.key === activeTab) ?? TABS[0]
  const tasks = useMemo(
    () => allTasks.filter((t) => activeTabDef.statuses.includes(t.status)),
    [allTasks, activeTabDef],
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

  const storeReady = !storeLoading || projects.length > 0

  return (
    <div className="h-full flex flex-col relative bg-muted/30 overflow-hidden">
      <ExperimentNotice />
      {!storeReady && (
        <div className="absolute inset-0 z-30 flex items-center justify-center bg-muted/30">
          <div className="text-xs text-muted-foreground animate-pulse">
            正在恢复工作空间…
          </div>
        </div>
      )}
      <div className="flex-1 flex flex-col lg:flex-row gap-2 min-h-0 px-2.5 pt-2 pb-2 overflow-y-auto lg:overflow-hidden">

      {/* Left: queue — full height on wide, top strip on narrow */}
      <div className="w-full lg:w-[300px] xl:w-[360px] shrink-0 h-[280px] lg:h-full rounded-lg bg-background flex flex-col overflow-hidden">
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
          <div className="rounded-md bg-muted/40 px-2.5 py-1.5 flex items-center gap-2">
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
                            layout
                            initial={{ opacity: 0, y: 8 }}
                            animate={{ opacity: 1, y: 0 }}
                            transition={{ duration: 0.25 }}
                          >
                            <TaskRow
                              task={t}
                              suspended={g.statuses[0] === "__suspended__"}
                              selected={t.id === selectedId}
                              onSelect={() => setSelectedId(t.id)}
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
                      layout
                      initial={{ opacity: 0, y: 8 }}
                      animate={{ opacity: 1, y: 0 }}
                      transition={{ duration: 0.25 }}
                    >
                      <TaskRow
                        task={t}
                        selected={t.id === selectedId}
                        onSelect={() => setSelectedId(t.id)}
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
        <div className="shrink-0 p-2.5">
          <Button
            variant="outline"
            className="w-full gap-1.5 h-8 text-xs bg-muted/30 border-0"
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

      {/* Right zone: 无限画布工作台主体 */}
      <div className="flex-1 flex flex-col min-w-0 min-h-0 rounded-lg overflow-hidden border border-border/60 bg-background relative shadow-2xs">
        <AutonomousDutyCanvasApp
          hideSidebar={true}
          hideTopBar={true}
          externalSelectedTaskId={selectedId}
          onTaskSelect={(id) => {
            if (id) setSelectedId(id)
          }}
          renderInputBar={({ selectedTask, selectedTaskIds, isMultiSelected, onClearSelection }) => (
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
                  window.dispatchEvent(
                    new CustomEvent("canvas:node-chat", {
                      detail: { taskId: selectedTask.id, message: text, files },
                    }),
                  )
                } else {
                  window.dispatchEvent(
                    new CustomEvent("canvas:global-prompt", {
                      detail: { text, files },
                    }),
                  )
                }
              }}
              onStop={() => {}}
              isAgentWorking={false}
              isSending={false}
              isStopPending={false}
            />
          )}
        />
      </div>
    </div>

      {/* ── 底部：整页 KITT 往返扫描 ── */}
      <PulseWave active={dash.data?.duty_enabled === true} />

      {/* 浮动圆形启停按钮（FAB，悬浮于右下角控制条上方） */}
      <DutyStartStopButton onRitual={(ph) => setRitual(ph === "done" ? null : ph)} />

      {/* 值守启停转场仪式遮罩 */}
      {ritual && <DutyRitualOverlay phase={ritual} />}
    </div>
  )
}
