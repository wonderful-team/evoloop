/* Demo runtime engine: drives the duty workbench like a live Agent.
 * Reveals messages over time, advances plan steps, flows tasks through
 * the status machine, accumulates tokens — everything ticks. */

import type { QueueTask } from "@/lib/tasksQueueApi"
import {
  demoDashboard,
  demoMessages,
  demoMessagesOld2,
  demoGenMessages,
  demoPlanMap,
  demoTasks,
  demoHistoryTasks,
  demoCreativeTasks,
} from "./demoData"

type Msg = Record<string, unknown>

interface Script {
  threadId: string
  taskId: string
  messages: Msg[]
  /** message index thresholds at which each plan step completes */
  stepDoneAt: number[]
}

const SCRIPTS: Script[] = [
  {
    threadId: "thread-demo",
    taskId: "t-demo-4",
    messages: demoMessages as Msg[],
    stepDoneAt: [7, 12, 21, 23],
  },
  {
    threadId: "thread-demo-old",
    taskId: "t-demo-3",
    messages: [
      { id: "od01", role: "ai", content: "开始订单巡检：核对过去 30 分钟新增订单的发货时效与付款状态。" },
      { id: "od02", role: "assistant", name: "list_orders", tool_calls: [{ name: "list_orders" }], content: '{"since":"30m"}' },
      { id: "od03", role: "tool", name: "list_orders", content: "新增订单 6 笔，其中 1 笔待付款超 25 分钟" },
      { id: "od04", role: "ai", content: "6 笔订单 5 笔正常，1 笔待付款即将超时，先发送催付提醒。" },
      { id: "od05", role: "assistant", name: "send_payment_reminder", tool_calls: [{ name: "send_payment_reminder" }], content: '{"order_id":"SO-2231"}' },
      { id: "od06", role: "tool", name: "send_payment_reminder", content: "催付短信已发送至订单 SO-2231 买家" },
      { id: "od07", role: "ai", content: "已写入巡检结论：本轮无异常订单，1 笔已触发催付。生成报告。" },
      { id: "od08", role: "assistant", name: "write_report", tool_calls: [{ name: "write_report" }], content: '{"path":"reports/order-patrol-1102.md"}' },
      { id: "od09", role: "tool", name: "write_report", content: "报告已写入 reports/order-patrol-1102.md（6 单扫描、1 单催付）" },
      { id: "od10", role: "ai", content: "订单巡检完成：全部正常。自检通过，T4 级无需人工介入，任务进入待验收。" },
    ],
    stepDoneAt: [3, 6, 10],
  },
  {
    threadId: "thread-member-run",
    taskId: "t-demo-5",
    messages: [
      { id: "mb01", role: "ai", content: "开始会员巡检：核对新入会成员的权益发放完整性。" },
      { id: "mb02", role: "assistant", name: "list_new_members", tool_calls: [{ name: "list_new_members" }], content: '{"since":"today"}' },
      { id: "mb03", role: "tool", name: "list_new_members", content: "今日新增会员 4 人" },
      { id: "mb04", role: "assistant", name: "check_benefits", tool_calls: [{ name: "check_benefits" }], content: '{"members":4}' },
      { id: "mb05", role: "tool", name: "check_benefits", content: "3 人权益已到账，1 人（手机尾号 8823）优惠券未发放" },
      { id: "mb06", role: "assistant", name: "grant_coupon", tool_calls: [{ name: "grant_coupon" }], content: '{"member_id":"m-8823","coupon":"newbie-pack"}' },
      { id: "mb07", role: "tool", name: "grant_coupon", content: "新人礼包已补发成功" },
      { id: "mb08", role: "ai", content: "会员巡检完成：4 人权益全部到账（含 1 例补发）。自检通过，任务进入待验收。" },
    ],
    stepDoneAt: [3, 6, 8],
  },
]

const idle = () => ({
  counts: {
    proposed: 2,
    pending: 3,
    in_progress: 1,
    waiting_acceptance: 2,
    completed: 2,
    failed: 1,
    cancelled: 0,
  },
})

type RunInfo = {
  thread_id: string
  goal: string
  started_at: string
  input_tokens: number
  output_tokens: number
}

type Dash = {
  counts: Record<string, number>
  duty_state: "busy" | "idle" | "error"
  tokens: {
    today: { input: number; output: number; llm_calls: number }
    week: { input: number; output: number; llm_calls: number }
  }
  today_window: { since: string | null; until: string | null }
  daily: {
    date: string
    input_tokens: number
    output_tokens: number
    completed: number
  }[]
  recent_events: {
    at: string | null
    kind: string
    title: string | null
    status: string
    task_id: string
    result: string
  }[]
  current_run: RunInfo | null
}

interface RuntimeState {
  dashboard: Dash
  tasks: QueueTask[]
  messagesByThread: Record<string, Msg[]>
  events: Dash["recent_events"]
}

let state: RuntimeState | null = null
let timer: ReturnType<typeof setInterval> | null = null
let scriptIdx = 0
let msgCursor = 0
let tickCount = 0
let running = false
const shownMessages = new Set<string>()
const pulse: number[] = []
const toolCounts: Record<string, number> = {
  list_goods: 14,
  check_stock: 12,
  update_stock: 9,
  text2image: 6,
  write_report: 11,
  list_orders: 16,
  send_payment_reminder: 5,
}

export function getDemoPulse(): number[] {
  return [...pulse]
}
export function getDemoToolCounts(): Record<string, number> {
  return { ...toolCounts }
}
export function getDemoTaskCounter(): number {
  return taskCounter
}
let taskCounter = 3

export function getDemoRunning() {
  return running
}

/** FAB-driven start/stop. Stop freezes the scene; start resumes. */
export function setDemoRunning(next: boolean) {
  if (next === running) return
  running = next
  const s = snap()
  if (next) {
    // claim current script task if nothing is running
    const script = SCRIPTS[scriptIdx]
    const task = s.tasks.find((t) => t.id === script.taskId)
    if (task && task.status === "pending") {
      task.status = "in_progress"
      task.last_thread_id = script.threadId
    }
    const runningTask = s.tasks.find((t) => t.status === "in_progress")
    s.dashboard.duty_state = "busy"
    s.dashboard.today_window.since =
      s.dashboard.today_window.since ?? nowIso()
    if (runningTask) {
      s.dashboard.current_run = {
        thread_id: runningTask.last_thread_id ?? script.threadId,
        goal: runningTask.description ?? runningTask.title ?? "",
        started_at: nowIso(),
        input_tokens: 0,
        output_tokens: 0,
      }
      pushEvent(
        "progress",
        runningTask.title ?? "",
        "in_progress",
        runningTask.id,
        "值守开启，Agent 领取任务",
      )
    }
    if (!timer) timer = setInterval(tick, 450)
  } else {
    s.dashboard.duty_state = "idle"
    s.dashboard.current_run = null
    pushEvent("progress", "值守", "idle", "-", "值守已停止，现场冻结")
    if (timer) {
      clearInterval(timer)
      timer = null
    }
  }
}

function snap(): RuntimeState {
  if (!state) {
    state = {
      dashboard: JSON.parse(JSON.stringify(demoDashboard)),
      tasks: JSON.parse(
        JSON.stringify([...demoTasks, ...demoHistoryTasks, ...demoCreativeTasks]),
      ),
      messagesByThread: JSON.parse(
        JSON.stringify({
          "thread-demo": demoMessages,
          "thread-demo-old2": demoMessagesOld2,
          ...demoGenMessages,
        }),
      ),
      events: JSON.parse(JSON.stringify(demoDashboard.recent_events)),
    }
  }
  return state
}

// always return fresh references so react-query picks up changes
export function getDemoDashboard(): Dash {
  return JSON.parse(JSON.stringify(snap().dashboard))
}
export function getDemoTasks(): { items: QueueTask[]; count: number } {
  const tasks = JSON.parse(JSON.stringify(snap().tasks)) as QueueTask[]
  return { items: tasks, count: tasks.length }
}
export function getDemoMessages(threadId: string | null): { messages: Msg[] } {
  const s = snap()
  return JSON.parse(
    JSON.stringify({ messages: s.messagesByThread[threadId ?? ""] ?? [] }),
  )
}
export function getDemoPlan(threadId: string | null) {
  const plan =
    (threadId && demoPlanMap[threadId]) || demoPlanMap["thread-demo"]
  return JSON.parse(JSON.stringify(plan))
}

function guessTool(script: Script, msgId: string): string {
  const m = script.messages.find((x) => String(x.id) === msgId)
  const name = (m as { name?: string } | undefined)?.name
  return name ?? ""
}

function nowIso() {
  return new Date().toISOString()
}

function pushEvent(
  kind: string,
  title: string,
  status: string,
  taskId: string,
  result: string,
) {
  const s = snap()
  s.events.unshift({
    at: nowIso(),
    kind,
    title,
    status,
    task_id: taskId,
    result,
  })
  if (s.events.length > 12) s.events.pop()
}

function recomputeCounts(s: RuntimeState) {
  const counts: Record<string, number> = {
    proposed: 0,
    pending: 0,
    in_progress: 0,
    waiting_acceptance: 0,
    completed: 0,
    failed: 0,
    cancelled: 0,
  }
  for (const t of s.tasks) counts[t.status] = (counts[t.status] ?? 0) + 1
  s.dashboard.counts = counts
}

function completeCurrentScript(s: RuntimeState, script: Script) {
  const task = s.tasks.find((t) => t.id === script.taskId)
  if (task) {
    task.status = "completed"
    task.self_check = { verdict: "pass", notes: "自动巡检通过" }
    task.acceptance = { by: "system:auto" }
  }
  pushEvent(
    "acceptance",
    task?.title ?? script.taskId,
    "completed",
    script.taskId,
    "自检通过，自动验收完成",
  )
  taskCounter += 1
  // advance: next pending task becomes in_progress with its script
  const nextIdx = scriptIdx + 1
  msgCursor = 0
  shownMessages.clear()
  if (nextIdx >= SCRIPTS.length) {
    // all scripts done → duty winds down naturally, list stays stable
    running = false
    if (timer) {
      clearInterval(timer)
      timer = null
    }
    s.dashboard.duty_state = "idle"
    s.dashboard.current_run = null
    pushEvent("progress", "值守", "idle", "-", "本轮巡检全部完成")
    return
  }
  scriptIdx = nextIdx
  const next = SCRIPTS[scriptIdx]
  const nextTask = s.tasks.find((t) => t.id === next.taskId)
  if (nextTask && nextTask.status === "pending") {
    nextTask.status = "in_progress"
    nextTask.last_thread_id = next.threadId
    pushEvent(
      "progress",
      nextTask.title ?? "",
      "in_progress",
      next.taskId,
      "Agent 领取任务，开始执行",
    )
    s.dashboard.current_run = {
      thread_id: next.threadId,
      goal: nextTask.description ?? nextTask.title ?? "",
      started_at: nowIso(),
      input_tokens: 0,
      output_tokens: 0,
    }
  }
  recomputeCounts(s)
}

function tick() {
  tickCount += 1
  const s = snap()
  const script = SCRIPTS[scriptIdx]

  // 1) tokens accumulate every tick (both KPI and current run)
  const dIn = 280 + Math.floor(Math.random() * 640)
  const dOut = 90 + Math.floor(Math.random() * 320)
  pulse.push(dIn + dOut)
  if (pulse.length > 60) pulse.shift()
  s.dashboard.tokens.today.input += dIn
  s.dashboard.tokens.today.output += dOut
  s.dashboard.tokens.today.llm_calls += 1
  s.dashboard.tokens.week.input += dIn
  s.dashboard.tokens.week.output += dOut
  s.dashboard.tokens.week.llm_calls += 1
  if (s.dashboard.current_run) {
    s.dashboard.current_run.input_tokens += dIn
    s.dashboard.current_run.output_tokens += dOut
  }
  const today = s.dashboard.daily[s.dashboard.daily.length - 1]
  if (today) {
    today.input_tokens += dIn
    today.output_tokens += dOut
  }

  // 2) reveal next script message every 2 ticks (~5s)
  if (tickCount % 3 === 0 && msgCursor < script.messages.length) {
    const m = script.messages[msgCursor]
    msgCursor += 1
    if (!shownMessages.has(String(m.id))) {
      shownMessages.add(String(m.id))
      const thread = s.messagesByThread[script.threadId] ?? []
      if (thread.some((x) => String(x.id) === String(m.id))) return
      thread.push(m)
      s.messagesByThread[script.threadId] = thread
      if (m.role === "tool") {
        const tool = guessTool(script, String(m.id))
        if (tool) toolCounts[tool] = (toolCounts[tool] ?? 0) + 1
        pushEvent(
          "progress",
          s.tasks.find((t) => t.id === script.taskId)?.title ?? "",
          "in_progress",
          script.taskId,
          String(m.content ?? "").slice(0, 40),
        )
      }
    }
  }

  // 3) plan steps advance with message progress
  const plan = demoPlanMap[script.threadId]?.plan as
    | { steps?: { status: string }[] }
    | undefined
  if (plan?.steps) {
    plan.steps.forEach((st, i) => {
      const threshold = script.stepDoneAt[i] ?? script.messages.length
      if (msgCursor >= threshold && st.status === "pending") {
        st.status = "in_progress"
      }
      // steps before the current threshold are done
      const prev = script.stepDoneAt[i - 1] ?? 0
      if (msgCursor >= threshold && msgCursor >= prev && st.status === "in_progress") {
        st.status = "completed"
      }
    })
    // mark first unfinished as in_progress for the "current step" view
    const firstUnfinished = plan.steps.find((st) => st.status !== "completed")
    if (firstUnfinished && firstUnfinished.status === "pending") {
      firstUnfinished.status = "in_progress"
    }
  }

  // 4) script finished → complete task, start next
  if (msgCursor >= script.messages.length && tickCount % 3 === 0) {
    completeCurrentScript(s, script)
  }

  // 5) duty window: ensure "since" is set
  if (!s.dashboard.today_window.since) {
    s.dashboard.today_window.since = nowIso()
  }

}

/** demo mode: create a task from the form */
export function addDemoTask(input: {
  title: string
  description: string
  category: string
  priority: string
  risk_level: string
  type: string
}) {
  const s = snap()
  const id = `t-demo-new-${Date.now()}`
  s.tasks.unshift({
    id,
    title: input.title,
    description: input.description,
    type: input.type,
    status: "pending",
    category: input.category,
    priority: input.priority,
    risk_level: input.risk_level,
    source: "user",
    provenance: null,
    self_check: null,
    acceptance: null,
    due_at: null,
    last_thread_id: null,
  })
  recomputeCounts(s)
  pushEvent("proposal", input.title, "pending", id, "运营者手动创建")
  return id
}

/** Idempotent start (page mounts). ~0.45s heartbeat. */
export function startDemoRuntime() {
  if (timer) return
  timer = setInterval(tick, 2500)
}
export function stopDemoRuntime() {
  if (timer) {
    clearInterval(timer)
    timer = null
  }
}

// recompute initial idle counts so demo opens consistent
Object.assign(snap().dashboard, idle())
recomputeCounts(snap())
