import { useEffect, useMemo, useState } from "react"
import { motion } from "framer-motion"
import { useNavigate } from "@tanstack/react-router"
import { useChatStore } from "@/stores/chatStore"
import { useQuery, useQueryClient } from "@tanstack/react-query"
import {
  CheckCircle2,
  Inbox,
  Loader2,
  MonitorPlay,
  Plus,
} from "lucide-react"
import { useTranslation } from "react-i18next"

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
import { fmtDuration } from "./fmt"
import {
  TasksQueueApi,
  type QueueTask,
  type DashboardKpis,
} from "@/lib/tasksQueueApi"
import { DEMO } from "@/components/Duty/demoData"
import { getDemoDashboard, getDemoTasks } from "@/components/Duty/demoRuntime"
import { ExperimentNotice } from "@/components/Duty/ExperimentNotice"
import { PlanPanel } from "@/components/Duty/PlanPanel"
import { ExecutionPanel } from "@/components/Duty/ExecutionPanel"
import { CostBlock, PulseWave } from "@/components/Duty/AgentPulse"
import {
  DutyRitualOverlay,
  DutyStartStopButton,
} from "@/components/Duty/DutyStartStopButton"
import { ProjectSwitcher } from "@/components/Sidebar/ProjectSwitcher"
import { useProjectStore } from "@/stores/projectStore"

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

function useNow(intervalMs = 1000): number {
  const [now, setNow] = useState(() => Date.now())
  useEffect(() => {
    const iv = setInterval(() => setNow(Date.now()), intervalMs)
    return () => clearInterval(iv)
  }, [intervalMs])
  return now
}

/** Section header: colored dot + label + count + optional extra */
function PanelHead({
  dotCls,
  label,
  count,
  extra,
}: {
  dotCls?: string
  label: string
  count?: number | string
  extra?: React.ReactNode
}) {
  return (
    <div className="flex items-center gap-2 px-3 h-10 shrink-0">
      <span
        className={`inline-block h-1.5 w-1.5 rounded-full ${dotCls ?? "bg-primary"}`}
      />
      <span className="text-xs font-semibold tracking-wide">{label}</span>
      {count !== undefined && (
        <span className="font-mono text-[10px] text-muted-foreground">
          {count}
        </span>
      )}
      <span className="flex-1" />
      {extra}
    </div>
  )
}

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

  const now = useNow()
  const projects = useProjectStore((st) => st.projects)
  const storeLoading = useProjectStore((st) => st.isLoading)
  const currentRun = dash.data?.current_run
  useEffect(() => {
    setSelectedId(null)
  }, [projectId])
  // 右列永远跟随当前 Tab：显式选中须属于本 Tab，否则回落到 Tab 内首个任务
  const selected = useMemo(() => {
    if (selectedId) {
      const hit = allTasks.find((t) => t.id === selectedId)
      if (hit && activeTabDef.statuses.includes(hit.status)) return hit
    }
    const pool = allTasks.filter((t) =>
      activeTabDef.statuses.includes(t.status),
    )
    return pool.find((t) => t.status === "in_progress") ?? pool[0] ?? null
  }, [allTasks, selectedId, activeTabDef])

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
      <div className="flex-1 flex flex-col lg:flex-row gap-2 min-h-0 px-3 pt-3 overflow-y-auto lg:overflow-hidden">

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
            className="px-1 py-1.5 space-y-3 animate-in fade-in slide-in-from-bottom-1 duration-200"
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

      {/* Right zone: KPI + columns + week strip */}
      <div className="flex-1 flex flex-col min-w-0 min-h-0 overflow-hidden">
        <div className="flex-1 flex flex-col lg:flex-row gap-2 overflow-hidden min-h-0">
          {/* Middle: distribution + trend + plan */}
          <div className="w-full lg:w-[320px] xl:w-[380px] shrink-0 h-[45%] lg:h-auto rounded-lg bg-background flex flex-col overflow-hidden">
            <ScrollArea className="flex-1">
              <div className="p-3 space-y-3">
                {/* ── Needs you: actionable items ── */}
                <div>
                  <div className="text-[11px] font-medium text-muted-foreground mb-1.5 flex items-center gap-1.5">
                    <span className="inline-block h-1.5 w-1.5 rounded-full bg-amber-500 animate-pulse" />
                    需要你处理
                  </div>
                  <div className="space-y-1.5">
                    {(() => {
                      const hitlItems = (hitlPending.data?.items ?? []).filter(
                        (h) => h.task_id,
                      )
                      const needGroups: {
                        key: string
                        label: string
                        cls: string
                        items: QueueTask[]
                        action: string
                      }[] = [
                        { key: "proposed", label: "待确认提案", cls: "text-violet-600 dark:text-violet-400", items: allTasks.filter((t) => t.status === "proposed"), action: "去确认" },
                        { key: "waiting", label: "待验收", cls: "text-amber-600 dark:text-amber-400", items: allTasks.filter((t) => t.status === "waiting_acceptance"), action: "去验收" },
                        { key: "failed", label: "失败需关注", cls: "text-destructive", items: allTasks.filter((t) => t.status === "failed"), action: "重跑" },
                      ]
                      const total = needGroups.reduce((n, g) => n + g.items.length, 0)
                                            if (hitlItems.length > 0) {
                        return (
                          <div className="space-y-1.5">
                            <div className="rounded-md bg-amber-500/5 px-2.5 py-2">
                              <div className="flex items-center gap-1.5 text-[11px] mb-1">
                                <span className="font-medium text-amber-600 dark:text-amber-400">
                                  等待审批 · {hitlItems.length}
                                </span>
                              </div>
                              {hitlItems.slice(0, 3).map((h) => (
                                <button
                                  key={h.request_id}
                                  className="w-full flex items-center gap-1.5 py-1 text-left group"
                                  onClick={() => {
                                    if (h.task_id) {
                                      setSelectedId(h.task_id)
                                      const tab = TABS.find((tb) =>
                                        tb.statuses.includes(
                                          allTasks.find((t) => t.id === h.task_id)
                                            ?.status ?? "",
                                        ),
                                      )
                                      if (tab) setActiveTab(tab.key)
                                    }
                                  }}
                                >
                                  <span className="text-xs truncate flex-1">
                                    {h.task_title ?? h.description}
                                  </span>
                                  <span className="text-[10px] text-amber-600 dark:text-amber-400 shrink-0 group-hover:opacity-100 opacity-70">
                                    去审批 →
                                  </span>
                                </button>
                              ))}
                            </div>
                            {needGroups
                              .filter((g) => g.items.length > 0)
                              .map((g) => (
                                <div key={g.key} className="rounded-md bg-muted/30 px-2.5 py-2">
                                  <div className="flex items-center gap-1.5 text-[11px] mb-1">
                                    <span className={`font-medium ${g.cls}`}>
                                      {g.label} · {g.items.length}
                                    </span>
                                  </div>
                                  {g.items.slice(0, 3).map((t) => (
                                    <button
                                      key={t.id}
                                      className="w-full flex items-center gap-1.5 py-1 text-left group"
                                      onClick={async () => {
                                        if (g.key === "failed") {
                                          await TasksQueueApi.rerun(t.id).catch(() =>
                                            TasksQueueApi.update(t.id, {
                                              status: "pending",
                                            }),
                                          )
                                          await invalidate()
                                          return
                                        }
                                        setSelectedId(t.id)
                                        const tab = TABS.find((tb) =>
                                          tb.statuses.includes(t.status),
                                        )
                                        if (tab) setActiveTab(tab.key)
                                      }}
                                    >
                                      <span className="text-xs truncate flex-1 group-hover:text-primary transition-colors">
                                        {t.title}
                                      </span>
                                      <span className="text-[10px] text-primary shrink-0 opacity-0 group-hover:opacity-100 transition-opacity">
                                        {g.action} →
                                      </span>
                                    </button>
                                  ))}
                                </div>
                              ))}
                          </div>
                        )
                      }
                      if (total === 0) {
                        return (
                          <div className="rounded-md bg-emerald-500/5 px-3 py-3 text-xs text-emerald-600 dark:text-emerald-400 flex items-center gap-1.5">
                            <CheckCircle2 className="h-3.5 w-3.5" />
                            全部处理完毕，Agent 正在值守
                          </div>
                        )
                      }
                      return needGroups.map((g) =>
                        g.items.length === 0 ? null : (
                          <div key={g.key} className="rounded-md bg-muted/30 px-2.5 py-2">
                            <div className="flex items-center gap-1.5 text-[11px] mb-1">
                              <span className={`font-medium ${g.cls}`}>
                                {g.label} · {g.items.length}
                              </span>
                            </div>
                            {g.items.slice(0, 3).map((t) => (
                              <button
                                key={t.id}
                                className="w-full flex items-center gap-1.5 py-1 text-left group"
                                onClick={async () => {
                                  if (g.key === "failed") {
                                    await TasksQueueApi.rerun(t.id).catch(() =>
                                      TasksQueueApi.update(t.id, {
                                        status: "pending",
                                      }),
                                    )
                                    await invalidate()
                                    return
                                  }
                                  setSelectedId(t.id)
                                  const tab = TABS.find((tb) =>
                                    tb.statuses.includes(t.status),
                                  )
                                  if (tab) setActiveTab(tab.key)
                                }}
                              >
                                <span className="text-xs truncate flex-1 group-hover:text-primary transition-colors">
                                  {t.title}
                                </span>
                                <span className="text-[10px] text-primary shrink-0 opacity-0 group-hover:opacity-100 transition-opacity">
                                  {g.action} →
                                </span>
                              </button>
                            ))}
                            {g.items.length > 3 && (
                              <div className="text-[10px] text-muted-foreground/60">
                                …以及 {g.items.length - 3} 项
                              </div>
                            )}
                          </div>
                        ),
                      )
                    })()}
                  </div>
                </div>

                {/* plan of selected task */}
                <div
                  key={`plan-${selected?.id ?? "none"}`}
                  className="border-t pt-2 animate-in fade-in slide-in-from-bottom-1 duration-300"
                >
                  <div className="text-[11px] font-medium text-muted-foreground mb-1.5 flex items-center gap-1.5">
                    <span className="inline-block h-1 w-1 rounded-full bg-primary" />
                    {t("dutyBoard.plan.title")}
                  </div>
                  {selected ? (
                    <PlanPanel task={selected} />
                  ) : (
                    <div className="text-xs text-muted-foreground/60 py-3">
                      {t("dutyBoard.plan.selectHint")}
                    </div>
                  )}
                </div>
              </div>
            </ScrollArea>
            {/* 成本块：中列底部固定 */}
            <div className="shrink-0 border-t px-3 py-2.5">
              <CostBlock dashboard={dash.data} now={now} />
            </div>
          </div>

          {/* Right: live execution */}
          <div className="flex-1 rounded-lg bg-background flex flex-col overflow-hidden min-w-0">
            <PanelHead
              dotCls={currentRun ? "bg-primary animate-pulse" : "bg-muted-foreground/40"}
              label={t("dutyBoard.exec.title")}
              extra={
                currentRun ? (
                  <span className="flex items-center gap-1.5 text-xs font-medium text-primary">
                    <Loader2 className="h-3 w-3 animate-spin" />
                    {t("dutyBoard.running")}
                    <span className="font-mono tabular-nums">
                      {fmtDuration(currentRun.started_at, now)}
                    </span>
                  </span>
                ) : undefined
              }
            />
            <ScrollArea className="flex-1">
              {selected ? (
                <div
                  key={`exec-${selected.id}`}
                  className="p-3 animate-in fade-in slide-in-from-right-2 duration-300"
                >
                  <ExecutionPanel
                    task={selected}
                    hitlPending={
                      (hitlPending.data?.items ?? []).filter(
                        (h) => h.task_id === selected.id,
                      )
                    }
                    sourceTask={
                      selected.provenance &&
                      typeof selected.provenance === "object" &&
                      (selected.provenance as { task_id?: string }).task_id
                        ? allTasks.find(
                            (t) =>
                              t.id ===
                              (selected.provenance as { task_id?: string })
                                .task_id,
                          ) ?? null
                        : null
                    }
                    relatedProposals={allTasks.filter(
                      (t) =>
                        (t.provenance as { task_id?: string } | null)
                          ?.task_id === selected.id,
                    )}
                    runTokens={
                      currentRun &&
                      selected.status === "in_progress" &&
                      currentRun.thread_id === selected.last_thread_id
                        ? currentRun.input_tokens + currentRun.output_tokens
                        : null
                    }
                    onChanged={invalidate}
                    onConfirmed={async () => {
                      await invalidate()
                      setActiveTab("pending")
                      await qc.invalidateQueries({ queryKey: ["dutyQueue"] })
                    }}
                  />
                </div>
              ) : (
                <div className="h-full flex flex-col items-center justify-center gap-3 py-16 text-center">
                  <MonitorPlay className="h-8 w-8 text-muted-foreground/30" />
                  <div className="text-sm text-muted-foreground">
                    {t("dutyBoard.plan.selectHint")}
                  </div>
                  <p className="text-xs text-muted-foreground/60 max-w-[280px]">
                    {t("dutyBoard.hint")}
                  </p>
                </div>
              )}
            </ScrollArea>
          </div>
        </div>
      </div>
      </div>

      {/* ── 底部：整页 KITT 往返扫描 ── */}
      <PulseWave active={dash.data?.duty_enabled === true} />

      {/* floating duty start/stop — page root, exactly one */}
      {ritual && <DutyRitualOverlay phase={ritual} />}
      <DutyStartStopButton onRitual={(ph) => setRitual(ph === "done" ? null : ph)} />
    </div>
  )
}
