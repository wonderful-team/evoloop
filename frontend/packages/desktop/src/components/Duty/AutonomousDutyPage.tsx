import { useEffect, useMemo, useState } from "react"
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

import { Badge } from "@evoloop/shared/components/ui/badge"
import { Button } from "@evoloop/shared/components/ui/button"
import { ScrollArea } from "@evoloop/shared/components/ui/scroll-area"

import {
  TasksQueueApi,
  type QueueTask,
  type DashboardKpis,
} from "@/lib/tasksQueueApi"
import { DEMO } from "@/components/Duty/demoData"
import { getDemoDashboard, getDemoTasks } from "@/components/Duty/demoRuntime"
import { ExperimentNotice } from "@/components/Duty/ExperimentNotice"
import { PlanPanel, PlanProgressInline } from "@/components/Duty/PlanPanel"
import { ExecutionPanel } from "@/components/Duty/ExecutionPanel"
import {
  CostBlock,
  PulseWave,
} from "@/components/Duty/AgentPulse"
import {
  DutyRitualOverlay,
  DutyStartStopButton,
} from "@/components/Duty/DutyStartStopButton"

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

const RISK_STYLES: Record<string, string> = {
  T1: "bg-red-100 text-red-700 dark:bg-red-950 dark:text-red-300",
  T2: "bg-orange-100 text-orange-700 dark:bg-orange-950 dark:text-orange-300",
  T3: "bg-blue-100 text-blue-700 dark:bg-blue-950 dark:text-blue-300",
  T4: "bg-gray-100 text-gray-600 dark:bg-gray-900 dark:text-gray-300",
}

function fmtDuration(fromIso: string | null, now: number = Date.now()): string {
  if (!fromIso) return "—"
  const ms = now - new Date(fromIso).getTime()
  if (ms <= 0) return "0m"
  const m = Math.floor(ms / 60000)
  const sec = Math.floor((ms % 60000) / 1000)
  if (m < 60) return `${m}m ${String(sec).padStart(2, "0")}s`
  return `${Math.floor(m / 60)}h ${String(m % 60).padStart(2, "0")}m`
}

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

  const dash = useQuery<DashboardKpis>({
    queryKey: ["dutyDashboard"],
    queryFn: () =>
      DEMO ? Promise.resolve(getDemoDashboard()) : TasksQueueApi.dashboard(),
    refetchInterval: 5000,
  })

  const queue = useQuery<{ items: QueueTask[]; count: number }>({
    queryKey: ["dutyQueue"],
    queryFn: () =>
      DEMO ? Promise.resolve(getDemoTasks()) : TasksQueueApi.list(),
    refetchInterval: 5000,
  })

  const allTasks = useMemo(() => queue.data?.items ?? [], [queue.data])
  const activeTabDef = TABS.find((x) => x.key === activeTab) ?? TABS[0]
  const tasks = useMemo(
    () => allTasks.filter((t) => activeTabDef.statuses.includes(t.status)),
    [allTasks, activeTabDef],
  )

  const now = useNow()
  const currentRun = dash.data?.current_run
  const selected =
    allTasks.find((t) => t.id === selectedId) ??
    allTasks.find((t) => t.status === "in_progress") ??
    null

  async function invalidate() {
    await qc.invalidateQueries({ queryKey: ["dutyQueue"] })
    await qc.invalidateQueries({ queryKey: ["dutyDashboard"] })
  }

  return (
    <div className="h-full flex flex-col lg:flex-row relative bg-muted/30 overflow-hidden">
      <ExperimentNotice />

      {/* Left: queue — full height on wide, top strip on narrow */}
      <div className="w-full lg:w-[300px] xl:w-[360px] shrink-0 h-[280px] lg:h-full rounded-lg bg-background flex flex-col overflow-hidden">
        <PanelHead
          dotCls={activeTabDef.dotCls}
          label={activeTabDef.label}
          count={tasks.length}
        />
        <div className="flex flex-wrap items-center gap-1 px-2.5 py-1.5 shrink-0">
          {TABS.map((tab) => {
            const n = allTasks.filter((t) =>
              tab.statuses.includes(t.status),
            ).length
            const on = tab.key === activeTab
            return (
              <button
                key={tab.key}
                onClick={() => setActiveTab(tab.key)}
                className={`shrink-0 inline-flex items-center gap-1 rounded-full px-2.5 py-1 text-[11px] transition-colors ${
                  on
                    ? "bg-primary/10 text-primary font-medium"
                    : "text-muted-foreground hover:bg-muted/50"
                }`}
              >
                <span
                  className={`inline-block h-1 w-1 rounded-full ${tab.dotCls} ${on ? "" : "opacity-50"}`}
                />
                {tab.label}
                <span className="font-mono text-[10px] opacity-70">{n}</span>
              </button>
            )
          })}
        </div>
        <ScrollArea className="flex-1">
          <div
            key={activeTab}
            className="p-2.5 space-y-1.5 animate-in fade-in slide-in-from-bottom-1 duration-200"
          >
              {activeTabDef.groups
                ? activeTabDef.groups.map((g) => {
                    const items = allTasks.filter((t) =>
                      g.statuses.includes(t.status),
                    )
                    if (items.length === 0) return null
                    return (
                      <div key={g.label} className="space-y-1.5">
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
                          <TaskRow
                            key={t.id}
                            task={t}
                            selected={t.id === selectedId}
                            onSelect={() => setSelectedId(t.id)}
                          />
                        ))}
                      </div>
                    )
                  })
                : tasks.map((t) => (
                    <TaskRow
                      key={t.id}
                      task={t}
                      selected={t.id === selectedId}
                      onSelect={() => setSelectedId(t.id)}
                    />
                  ))}
            {tasks.length === 0 && !queue.isLoading && (
              <div className="text-center text-xs text-muted-foreground py-12 space-y-1.5">
                <Inbox className="h-6 w-6 mx-auto opacity-40" />
                <p>{t("dutyBoard.empty")}</p>
              </div>
            )}
          </div>
        </ScrollArea>
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
        {/* Columns: charts | execution — side-by-side on wide, stacked on narrow */}
        <div className="flex-1 flex flex-col lg:flex-row gap-2 px-3 lg:px-4 overflow-hidden min-h-0">
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
                      const needGroups: {
                        key: string
                        label: string
                        cls: string
                        items: QueueTask[]
                        action: string
                      }[] = [
                        { key: "proposed", label: "待确认提案", cls: "text-violet-600 dark:text-violet-400", items: allTasks.filter((t) => t.status === "proposed"), action: "去确认" },
                        { key: "waiting", label: "待验收", cls: "text-amber-600 dark:text-amber-400", items: allTasks.filter((t) => t.status === "waiting_acceptance"), action: "去验收" },
                        { key: "failed", label: "失败需关注", cls: "text-destructive", items: allTasks.filter((t) => t.status === "failed"), action: "查看" },
                      ]
                      const total = needGroups.reduce((n, g) => n + g.items.length, 0)
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
                                onClick={() => {
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

        {/* Bottom row: cost (plan-aligned) + waveform (execution-aligned) */}
        <div className="shrink-0 grid grid-cols-1 lg:grid-cols-[320px_1fr] xl:grid-cols-[380px_1fr] gap-2 px-3 lg:px-4 pb-3 pt-2">
          <CostBlock />
          <PulseWave />
        </div>
      </div>

      {/* floating duty start/stop — page root, exactly one */}
      {ritual && <DutyRitualOverlay phase={ritual} />}
      <DutyStartStopButton onRitual={(ph) => setRitual(ph === "done" ? null : ph)} />
    </div>
  )
}

function TaskRow({
  task,
  selected,
  onSelect,
}: {
  task: QueueTask
  selected: boolean
  onSelect: () => void
}) {
  const { t } = useTranslation()
  const isRunning = task.status === "in_progress"
  const isProposal = task.status === "proposed"
  const isWaiting = task.status === "waiting_acceptance"
  const isFailed = task.status === "failed"

  const riskCls = RISK_STYLES[task.risk_level ?? "T3"] ?? RISK_STYLES.T3

  return (
    <div
      onClick={onSelect}
      className={`group rounded-md p-2.5 cursor-pointer transition-colors ${
        selected ? "bg-primary/10" : "bg-muted/30 hover:bg-muted/60"
      } ${isRunning ? "border-l-2 border-l-primary" : ""}`}
    >
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0 flex-1">
          <div className="text-[13px] font-medium truncate flex items-center gap-1.5">
            {isRunning && (
              <Loader2 className="h-3 w-3 animate-spin text-primary shrink-0" />
            )}
            {isProposal && (
              <span className="shrink-0 rounded-full bg-violet-500/10 text-violet-600 dark:text-violet-400 text-[9px] font-bold px-1.5 py-0.5">
                提案
              </span>
            )}
            {task.title}
          </div>
          {task.description && (
            <div className="text-[11px] text-muted-foreground line-clamp-1 mt-0.5">
              {task.description}
            </div>
          )}
          {isRunning && (
            <div className="mt-1.5">
              <PlanProgressInline task={task} />
            </div>
          )}
        </div>
        <div className="flex flex-col items-end gap-1 shrink-0">
          {task.risk_level && (
            <Badge className={`h-4.5 px-1.5 text-[10px] font-mono ${riskCls}`}>
              {task.risk_level}
            </Badge>
          )}
          {task.type === "recurring" && (
            <Badge
              variant="outline"
              className="h-4 px-1.5 text-[9px] tracking-wide"
            >
              {t("dutyBoard.recurring")}
            </Badge>
          )}
        </div>
      </div>

      <div className="mt-2 flex items-center gap-1.5 text-[10px] text-muted-foreground font-mono">
        {task.category && <span>{task.category}</span>}
        {task.priority && task.priority !== "medium" && (
          <Badge variant="outline" className="h-4 px-1 text-[9px]">
            {task.priority}
          </Badge>
        )}
        {isWaiting && (
          <span className="text-amber-600 dark:text-amber-400 font-sans font-medium">
            待验收 → 右侧处理
          </span>
        )}
        {isFailed && (
          <span className="text-destructive font-sans">失败</span>
        )}
        <span className="flex-1" />
        <span className="opacity-0 group-hover:opacity-60 transition-opacity">
          查看 →
        </span>
      </div>
    </div>
  )
}
