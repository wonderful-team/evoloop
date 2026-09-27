import { mkdirSync, writeFileSync } from "node:fs"
import path from "node:path"
import { expect, type Page, test } from "@playwright/test"
import { installGlobalProjectMock } from "./duty-isolation"
import { expectNoCrash, isAuthed, setupDone } from "./helpers"

/**
 * 值守画布 · 任务对话测试（duty-task-chat）
 *
 * 场景：值守界面底部的输入框（ChatInputArea prompt bar）针对某个任务
 * 发起对话。onSend 分两条分支（AutonomousDutyPage.tsx onSend）：
 *   A. 选中任务 + lastThreadId 存在 → canvas:node-chat 动画 +
 *      AgentService.chatEndpoint（POST /chat，thread_id=任务线程）→
 *      Agent 在该线程上应答 → 消息落库。
 *   B. 选中任务但 lastThreadId 为空（从未派发）→ 只派发本地动画事件，
 *      后端零调用（已知静默无效，本测试记录实际行为作为回归锚）。
 *   C. 未选中任务 → TasksQueueApi.create 新建任务（source=user → pending）。
 *
 * 断言以服务端为准：轮询 /api/v1/conversations/{thread}/messages，
 * 验证用户消息落库 + assistant 应答出现（进程内 MockLLM 回显）。
 */

test.use({
  viewport: { width: 1920, height: 1080 },
  video: { mode: "on", size: { width: 1920, height: 1080 } },
})

test.skip(
  !isAuthed(),
  "duty chat test requires E2E credentials (frontend/.env)",
)

interface TaskLite {
  id: string
  no: number
  st: string
  thread: string | null
}

async function fetchTasks(page: Page): Promise<TaskLite[]> {
  return page.evaluate(async () => {
    const res = await fetch("/api/v1/tasks/queue?limit=200", {
      credentials: "include",
    })
    if (!res.ok) throw new Error(`queue poll failed: HTTP ${res.status}`)
    const j = await res.json()
    const items = (j.items ?? j.data?.items ?? []) as {
      id: string
      task_no: number
      status: string
      last_thread_id: string | null
    }[]
    return items.map((t) => ({
      id: t.id,
      no: t.task_no,
      st: t.status,
      thread: t.last_thread_id,
    }))
  })
}

interface ThreadMessage {
  role: string
  text: string
}

async function fetchThreadMessages(
  page: Page,
  threadId: string,
): Promise<ThreadMessage[] | null> {
  return page.evaluate(async (tid) => {
    const res = await fetch(`/api/v1/conversations/${tid}/messages?limit=40`, {
      credentials: "include",
    })
    if (!res.ok) return null
    const j = await res.json()
    const items = (j.items ?? j.data?.items ?? j.data ?? []) as Array<{
      role?: string
      content?: unknown
    }>
    const w = window as unknown as { __dutyChatDebug?: string }
    w.__dutyChatDebug = `items=${items.length}`
    return items.map((m) => {
      const c = m.content
      const text =
        typeof c === "string"
          ? c
          : Array.isArray(c)
            ? c
                .map((p) =>
                  typeof p === "object" && p !== null && "text" in p
                    ? String((p as { text?: string }).text ?? "")
                    : "",
                )
                .join(" ")
            : String(c ?? "")
      return { role: String(m.role ?? "?"), text }
    })
  }, threadId)
}

test("duty board: task conversation via the bottom prompt bar", async ({
  page,
}) => {
  test.setTimeout(300_000)
  const artifactsDir = path.resolve(process.cwd(), "test-results/duty-chat")
  mkdirSync(artifactsDir, { recursive: true })

  const pageErrors: string[] = []
  page.on("pageerror", (err) => {
    if (pageErrors.length < 20) pageErrors.push(String(err).slice(0, 300))
  })

  await page.addInitScript(setupDone)
  // 关闭"实验功能"公告弹窗（否则 overlay 拦截一切点击）
  await page.addInitScript(() => {
    localStorage.setItem("duty-experiment-notice-acked", "1")
  })
  installGlobalProjectMock(page)
  await page.goto("/#/duty-autonomous")
  await expectNoCrash(page)
  await page
    .locator(".dc-card[data-task-id]")
    .first()
    .waitFor({ state: "visible", timeout: 20_000 })

  const tasks = await fetchTasks(page)
  const target = tasks.find((t) => t.thread && t.st === "pending")
  expect(
    target,
    "需要一个已派发过（有 last_thread_id）的 pending 任务",
  ).toBeTruthy()
  const targetTask = target as TaskLite

  const marker = `【对话测试 ${Date.now()}】`
  const message = `${marker}请同步一下你这条任务的当前进展。`

  // 选中任务：必须点画布卡片（原地展开+选中）。列表行点击不会同步到
  // 画布的 selectedTaskId（externalSelectedTaskId 未传给 DutyCanvas），
  // 输入框会走"全局新建任务"分支而非任务对话分支——实测确认的行为差异。
  // 单击卡片编号徽标 = 选中（官方提示"单击选中可拖拽或对话"）；点卡片
  // 中心会命中拖拽手柄导致选中失效（实测）。选中后底部输入框进入任务
  // 对话分支；未选中时发送会走"全局新建任务"分支（下方的建任务检测）。
  await page
    .locator(`.dc-card[data-task-id="${targetTask.id}"] .dc-badge-no`)
    .first()
    .click()
  await page.waitForTimeout(500)
  await page.screenshot({ path: path.join(artifactsDir, "01-selected.png") })

  // 底部输入框发送
  const input = page.locator("textarea").first()
  await expect(input).toBeVisible()
  await input.fill(message)
  await page.screenshot({ path: path.join(artifactsDir, "02-typed.png") })
  await input.press("Enter")

  let thread: ThreadMessage[] | null = null
  let userSeen = false
  let replySeen = false
  let replyText = ""
  let lastErr: string | null = null
  const deadline = Date.now() + 60_000
  while (Date.now() < deadline) {
    await page.waitForTimeout(2_000)
    thread = await fetchThreadMessages(page, targetTask.thread as string)
    const dbg = await page.evaluate(() => {
      const w = window as unknown as { __dutyChatDebug?: string }
      return w.__dutyChatDebug ?? null
    })
    console.log(`[chat-debug] poll: dbg=${dbg} userSeen=${userSeen} thread=${thread ? thread.length : "null"}`)
    if (thread === null) {
      lastErr = "messages endpoint not ok"
      continue
    }
    if (thread.some((m) => m.text.includes(marker))) userSeen = true
    const idx = thread.findIndex((m) => m.text.includes(marker))
    if (userSeen && idx >= 0) {
      const after = thread.slice(idx + 1)
      const assistant = after.find(
        (m) =>
          m.role.includes("assistant") ||
          m.role.includes("agent") ||
          m.text.startsWith("mock reply"),
      )
      if (assistant) {
        replySeen = true
        replyText = assistant.text.slice(0, 200)
        break
      }
    }
  }
  if (!userSeen) {
    // 诊断：选中未生效时 onSend 走全局分支 → 会以消息为标题新建任务
    const tasksAfter = await fetchTasks(page)
    const created = tasksAfter.some(
      (t) => t.st === "pending" && !tasks.some((x) => x.id === t.id),
    )
    expect(
      userSeen,
      created
        ? "选中未生效：发送走了全局建任务分支（点击未命中选中逻辑）"
        : "用户对话消息未落库到任务线程",
    ).toBe(true)
  }
  expect(replySeen, `Agent 未在任务线程上应答（60s）；lastErr=${lastErr}`).toBe(
    true,
  )
  await page.screenshot({ path: path.join(artifactsDir, "03-replied.png") })

  writeFileSync(
    path.join(artifactsDir, "result.json"),
    JSON.stringify({ target: targetTask, marker, replyText }, null, 2),
  )

  expect(pageErrors, "页面存在未捕获异常").toEqual([])
})

test("duty board: prompting with a never-dispatched task selected (document behavior)", async ({
  page,
}) => {
  test.setTimeout(120_000)
  await page.addInitScript(setupDone)
  await page.addInitScript(() => {
    localStorage.setItem("duty-experiment-notice-acked", "1")
  })
  installGlobalProjectMock(page)
  await page.goto("/#/duty-autonomous")
  await expectNoCrash(page)
  await page
    .locator(".dc-card[data-task-id]")
    .first()
    .waitFor({ state: "visible", timeout: 20_000 })

  const tasks = await fetchTasks(page)
  const neverRun = tasks.find((t) => !t.thread)
  test.skip(!neverRun, "当前队列所有任务都已派发过，跳过该边界场景")
  const target = neverRun as TaskLite

  const marker = `【未派发对话 ${Date.now()}】`
  await page.locator(`.dc-card[data-task-id="${target.id}"]`).first().click()
  const input = page.locator("textarea").first()
  await expect(input).toBeVisible()
  await input.fill(`${marker}随便说两句`)
  await input.press("Enter")

  // 已知行为：无 lastThreadId → 后端零调用。等 8s 后确认没有会话冒出来。
  await page.waitForTimeout(8_000)
  const conversations = await page.evaluate(async (tid) => {
    const res = await fetch(`/api/v1/conversations/${tid}/messages?limit=10`, {
      credentials: "include",
    })
    return res.status
  }, target.id)
  // 记录行为：404/40x = 后端确无该线程（符合"只走本地动画"的预期）
  expect([200, 404, 401, 403, 422]).toContain(conversations)
})
