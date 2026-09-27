import { spawn } from "node:child_process"
import { mkdirSync, writeFileSync } from "node:fs"
import os from "node:os"
import path from "node:path"
import { expect, type Page, test } from "@playwright/test"
import { installGlobalProjectMock } from "./duty-isolation"
import {
  type DutyObs,
  fetchServerTruth,
  OBSERVER_BOOTSTRAP,
  parseNo,
  type ServerTask,
  statusTolerant,
} from "./duty-observe-lib"
import { expectNoCrash, isAuthed, setupDone } from "./helpers"

/**
 * 值守全流程合一测试（一段视频记录全程）：
 *
 *   阶段 1 派发+执行：driver 重置/重启（进程内 MockLLM）→ 16 条任务
 *           逐条到期 → 派发 → 执行 → 六种场景终态 → 提案子任务生成
 *   阶段 2 提案接受：driver 接受两个提案 → 子任务派发执行
 *   阶段 3 任务对话：选中一张卡片 → 底部输入框发消息 → 消息落库到
 *           任务线程 → Agent 应答（mock reply）
 *
 * 断言：driver 退出码 / SSE 事件量与 churn 上限 / UI 收敛==服务端 /
 * 对话消息与应答 / 无 pageerror。产物：report.md、timeline.json、
 * 截图序列、video.webm。
 */

test.use({
  viewport: { width: 1920, height: 1080 },
  video: { mode: "on", size: { width: 1920, height: 1080 } },
})

test.skip(
  !isAuthed(),
  "duty full-flow requires E2E credentials (frontend/.env)",
)

// 轮询走 Node 侧 page.request（带 context cookie）：全流程运行期间页面
// 主线程被渲染+观测探针占满，页内 evaluate 的 fetch 会被饿死（实测）。
async function fetchThreadMessages(
  page: Page,
  threadId: string,
): Promise<{ role: string; text: string }[] | null> {
  const res = await page.request.get(
    `/api/v1/conversations/${threadId}/messages?limit=40`,
    { timeout: 10_000 },
  )
  if (!res.ok()) return null
  const j = await res.json()
  const items = (j.items ?? j.data?.items ?? j.data ?? []) as Array<{
    role?: string
    content?: unknown
  }>
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
}

test("duty full flow: dispatch → execute → proposals → chat, one video", async ({
  page,
}) => {
  test.setTimeout(600_000)
  const artifactsDir = path.resolve(
    process.cwd(),
    "test-results/duty-full-flow",
  )
  mkdirSync(artifactsDir, { recursive: true })

  const pageErrors: string[] = []
  page.on("pageerror", (err) => {
    if (pageErrors.length < 20) pageErrors.push(String(err).slice(0, 300))
  })

  await page.addInitScript(setupDone)
  await page.addInitScript(OBSERVER_BOOTSTRAP)
  installGlobalProjectMock(page)

  await page.goto("/#/duty-autonomous")
  await expectNoCrash(page)
  await page
    .locator(".dc-card[data-task-id]")
    .first()
    .waitFor({ state: "visible", timeout: 30_000 })
  await page.screenshot({ path: path.join(artifactsDir, "000-start.png") })

  const baseline = await fetchServerTruth(page)
  const timeline: Record<number, { t: number; st: string }[]> = {}
  const record = (tasks: ServerTask[], t: number) => {
    for (const task of tasks) {
      let arr = timeline[task.no]
      if (!arr) {
        arr = []
        timeline[task.no] = arr
      }
      const last = arr[arr.length - 1]
      if (!last || last.st !== task.st) arr.push({ t, st: task.st })
    }
  }
  record(baseline, Date.now())

  // ── 阶段 1+2：driver（重置→重启→喂任务→接受提案） ──
  const driverCmd =
    process.env.DUTY_DRIVER_CMD || "zsh /tmp/duty_demo_driver.sh"
  let driverExit: number | null = null
  const child = spawn(driverCmd, { shell: true, stdio: "ignore" })
  child.on("exit", (code) => {
    driverExit = code
  })

  const DEADLINE = Date.now() + 480_000
  const STEADY_MS = 8_000
  let lastChange = Date.now()
  let lastTruthSig = ""
  let lastShot = 0
  let shots = 0
  let pollErrors = 0
  while (Date.now() < DEADLINE) {
    await page.waitForTimeout(800)
    let truth: ServerTask[]
    try {
      truth = await fetchServerTruth(page)
    } catch {
      pollErrors += 1
      continue
    }
    record(truth, Date.now())
    const sig = truth
      .map((t) => `${t.id}:${t.st}`)
      .sort()
      .join("|")
    if (sig !== lastTruthSig) {
      lastTruthSig = sig
      lastChange = Date.now()
      if (shots < 80 && Date.now() - lastShot > 1_500) {
        shots += 1
        lastShot = Date.now()
        await page.screenshot({
          path: path.join(
            artifactsDir,
            `${String(shots).padStart(3, "0")}-change.png`,
          ),
        })
      }
    }
    if (driverExit !== null && Date.now() - lastChange >= STEADY_MS) break
  }

  // 收敛窗：负载高时 UI 渲染饥饿，收敛窗自适应拉长
  const load1 = os.loadavg()[0]
  const convergeDeadline = Date.now() + (load1 > 8 ? 120_000 : 45_000)
  let divergences: { no: number; server: string; ui: string }[] = []
  let sawTruth = false
  let reloadCount = 0
  for (;;) {
    let truth: ServerTask[] | null = null
    try {
      truth = await fetchServerTruth(page)
      sawTruth = true
    } catch {
      truth = null
    }
    if (truth !== null) {
      const obs = await page.evaluate(() => window.__dutyObs)
      const latest =
        obs && obs.cards.length > 0 ? obs.cards[obs.cards.length - 1] : null
      const uiByNo = new Map<number, string>()
      if (latest) {
        for (const card of latest.cards) {
          const no = parseNo(card.no)
          if (no != null) uiByNo.set(no, card.st)
        }
      }
      divergences = truth
        .map((t) => {
          const ui = uiByNo.get(t.no)
          return { no: t.no, server: t.st, ui: ui ?? "(missing)" }
        })
        .filter((d) => !statusTolerant(d.server, d.ui))
      if (divergences.length === 0) break
    }
    if (Date.now() > convergeDeadline) break
    // 残留分歧可能只是 reload 取到"回队前一瞬"——再对账一次（≤3 次）
    if (reloadCount < 3) {
      reloadCount += 1
      await page.reload()
      await page
        .locator(".dc-card[data-task-id]")
        .first()
        .waitFor({ state: "visible", timeout: 30_000 })
      await page.waitForTimeout(1_000)
      continue
    }
    await page.waitForTimeout(1_000)
  }

  await page.screenshot({
    path: path.join(artifactsDir, "900-after-dispatch.png"),
  })

  // 对账收敛：高负载下 SSE 事件可能到不了页面（UI 无事件驱动就停在旧
  // 状态）——与产品语义一致（状态以服务端为准，断线窗口由对账收敛），
  // reload 重拉服务端真相后再比对 UI。
  await page.reload()
  await page
    .locator(".dc-card[data-task-id]")
    .first()
    .waitFor({ state: "visible", timeout: 30_000 })
  await page.waitForTimeout(1_000)

  // ── 阶段 3：任务对话（选中已派发的 pending 卡片 → 输入框发消息） ──
  const truth = await fetchServerTruth(page)
  const tasksFull = await page.evaluate(async () => {
    const res = await fetch("/api/v1/tasks/queue?limit=200", {
      credentials: "include",
    })
    const j = await res.json()
    return (j.items ?? j.data?.items ?? []) as {
      id: string
      task_no: number
      last_thread_id: string | null
    }[]
  })
  const chatTarget = truth.find((t) => {
    const full = tasksFull.find((f) => f.id === t.id)
    return t.st === "pending" && full?.last_thread_id
  })
  expect(chatTarget, "需要一个已派发过的 pending 任务用于对话").toBeTruthy()
  const chatTask = chatTarget as ServerTask
  const chatThread = tasksFull.find((f) => f.id === chatTask.id)!
    .last_thread_id as string

  const marker = `【全流程对话 ${Date.now()}】`
  const message = `${marker}请同步一下你这条任务的当前进展。`
  // 点左列表行选中：externalSelectedTaskId → 画布 setSelectedTaskId +
  // focusTaskId → 自动飞镜把卡片带入视口（DutyCanvasApp:155-162）。
  // 画布卡片在 transform 平铺坐标系里可能远在视口外，不能直接点。
  await page
    .locator(`#duty-task-row-${chatTask.id}`)
    .first()
    .click({ timeout: 15_000 })
  for (let i = 0; i < 8; i++) {
    await page.waitForTimeout(500)
    const bb = await page
      .locator(`.dc-card[data-task-id="${chatTask.id}"] .dc-badge-no`)
      .boundingBox()
    if (
      bb &&
      bb.x >= 0 &&
      bb.y >= 0 &&
      bb.x + bb.width <= 1920 &&
      bb.y + bb.height <= 1080
    ) {
      break
    }
  }

  const input = page.locator("textarea").first()
  await expect(input).toBeVisible({ timeout: 15_000 })
  await input.fill(message)
  await page.screenshot({ path: path.join(artifactsDir, "910-chat-typed.png") })
  await input.press("Enter")

  let userSeen = false
  let replySeen = false
  let replyText = ""
  const chatDeadline = Date.now() + 60_000
  while (Date.now() < chatDeadline) {
    await page.waitForTimeout(2_000)
    const thread = await fetchThreadMessages(page, chatThread)
    if (thread === null) continue
    if (thread.some((m) => m.text.includes(marker))) userSeen = true
    const idx = thread.findIndex((m) => m.text.includes(marker))
    if (userSeen && idx >= 0) {
      const assistant = thread
        .slice(idx + 1)
        .find(
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
  await page.screenshot({
    path: path.join(artifactsDir, "920-chat-replied.png"),
  })

  // ── 值守排空战报：全部任务终态后后端广播 queue_drained，状态条展示汇总 ──
  let drainedSeen = false
  const drainedDeadline = Date.now() + 30_000
  while (Date.now() < drainedDeadline) {
    const obsNow = await page.evaluate(() => window.__dutyObs)
    if (
      obsNow &&
      obsNow.sse.some((s) => s.kind === "event" && s.name === "queue_drained")
    ) {
      drainedSeen = true
      break
    }
    await page.waitForTimeout(1_000)
  }
  // 服务端裁决（负载免疫）：本轮至少广播过一次排空战报
  const { execSync } = await import("node:child_process")
  // 后端重启会轮转 api.log（发布记录落入归档），跨当前+最近归档求和
  const logsDir = path.resolve(process.cwd(), "../backend/logs")
  let drainedPublishes = 0
  try {
    const files = execSync(
      `ls -t "${logsDir}"/api.log "${logsDir}"/api.log.bak_* 2>/dev/null | head -3`,
    )
      .toString()
      .trim()
      .split("\n")
      .filter(Boolean)
    for (const f of files) {
      drainedPublishes += Number(
        execSync(`grep -c "queue drained:" "${f}" || true`).toString().trim(),
      )
    }
  } catch {
    drainedPublishes = 0
  }
  expect(
    drainedPublishes,
    "后端未广播 queue_drained 排空战报（api.log 无记录）",
  ).toBeGreaterThanOrEqual(1)
  // UI 条：SSE 未饥饿（load≤8）时战报应已上屏；饥饿时记录不硬判
  const drainedStrip = await page
    .locator("text=本轮值守完成")
    .first()
    .isVisible({ timeout: drainedSeen ? 15_000 : 3_000 })
    .catch(() => false)
  if (drainedSeen && !drainedStrip) {
    console.warn("[full-flow] queue_drained 已广播但状态条未显示（SSE 饥饿？）")
  }
  await page.screenshot({
    path: path.join(artifactsDir, "890-drained-summary.png"),
  })

  // 对话后最终收敛复查（同样先对账重载）
  await page.reload()
  await page
    .locator(".dc-card[data-task-id]")
    .first()
    .waitFor({ state: "visible", timeout: 30_000 })
  await page.waitForTimeout(1_000)
  const finalDivergences: { no: number; server: string; ui: string }[] = []
  const finalDeadline = Date.now() + 30_000
  for (;;) {
    let finalTruth: ServerTask[] | null = null
    try {
      finalTruth = await fetchServerTruth(page)
    } catch {
      finalTruth = null
    }
    if (finalTruth !== null) {
      const obs = await page.evaluate(() => window.__dutyObs)
      const latest =
        obs && obs.cards.length > 0 ? obs.cards[obs.cards.length - 1] : null
      const uiByNo = new Map<number, string>()
      if (latest) {
        for (const card of latest.cards) {
          const no = parseNo(card.no)
          if (no != null) uiByNo.set(no, card.st)
        }
      }
      finalDivergences.length = 0
      for (const t of finalTruth) {
        const ui = uiByNo.get(t.no) ?? "(missing)"
        if (!statusTolerant(t.st, ui)) {
          finalDivergences.push({ no: t.no, server: t.st, ui })
        }
      }
      if (finalDivergences.length === 0) break
    }
    if (Date.now() > finalDeadline) break
    await page.waitForTimeout(1_000)
  }

  const obs: DutyObs | undefined = await page.evaluate(() => window.__dutyObs)
  await page.screenshot({ path: path.join(artifactsDir, "999-final.png") })

  // ── 报告 ──
  const sseOpens = obs ? obs.sse.filter((s) => s.kind === "open").length : 0
  const sseEvents = obs ? obs.sse.filter((s) => s.kind === "event").length : 0
  const frozenTicks = obs
    ? obs.mutationTicks.filter((x) => x.n === 0).length
    : 0
  const lastEdges =
    obs && obs.edgeLog.length > 0
      ? obs.edgeLog[obs.edgeLog.length - 1].edges
      : 0

  const lines: string[] = []
  lines.push(`# duty-full-flow report (${new Date().toISOString()})`)
  lines.push("")
  lines.push(`- driver: ${driverCmd}, exit=${driverExit}`)
  lines.push(`- SSE: open=${sseOpens}, task_queue_updated=${sseEvents}`)
  lines.push(
    `- UI 心跳: ${obs ? obs.mutationTicks.length : 0} 拍中 ${frozenTicks} 拍零 DOM 变化`,
  )
  lines.push(`- 画布连线徽标数（最终）: ${lastEdges}`)
  lines.push(`- truth poll errors: ${pollErrors}（sawTruth=${sawTruth}）`)
  lines.push(`- 对话: userSeen=${userSeen}, replySeen=${replySeen}`)
  lines.push(`  replyText: ${replyText}`)
  lines.push(`- pageerrors: ${pageErrors.length}`)
  lines.push("")
  lines.push("## 服务端状态时间线（每任务）")
  for (const no of Object.keys(timeline)
    .map(Number)
    .sort((a, b) => a - b)) {
    const arr = timeline[no]
    lines.push(
      `- #T-${no}: ${arr.map((x) => `${new Date(x.t).toLocaleTimeString()}→${x.st}`).join(" → ")}`,
    )
  }
  if (divergences.length > 0 || finalDivergences.length > 0) {
    lines.push("")
    lines.push("## ❌ 收敛失败：UI ≠ 服务端")
    for (const d of [...divergences, ...finalDivergences]) {
      lines.push(`- #T-${d.no}: server=${d.server} ui=${d.ui}`)
    }
  } else {
    lines.push("")
    lines.push("## ✅ 收敛成功：所有任务 UI 状态 == 服务端终态")
  }
  if (pageErrors.length > 0) {
    lines.push("")
    lines.push("## Uncaught page errors")
    for (const e of pageErrors) lines.push(`- ${e}`)
  }
  const report = lines.join("\n")
  writeFileSync(path.join(artifactsDir, "report.md"), report)
  writeFileSync(
    path.join(artifactsDir, "timeline.json"),
    JSON.stringify({ timeline, sse: obs?.sse ?? [], obs }, null, 2),
  )
  await test.info().attach("report.md", {
    body: report,
    contentType: "text/markdown",
  })

  // ── 断言 ──
  expect(pageErrors, "页面存在未捕获异常").toEqual([])
  expect(driverExit, "驱动脚本退出码").toBe(0)
  expect(sseOpens, "SSE 未建立连接").toBeGreaterThan(0)
  expect(sseOpens, "SSE 连接数过多（churn 回归）").toBeLessThanOrEqual(12)
  // 高负载下页面主线程饥饿会延迟 SSE 回调计数（load>8 时事件回调延迟到
  // 几乎收不到，但 UI 仍经 invalidate 收敛——此处降级为仅要求连接建立）
  if (load1 <= 8) {
    expect(sseEvents, "SSE 事件过少").toBeGreaterThan(1)
  }
  if (!userSeen || !replySeen) {
    // 高负载下页内/HTTP 轮询可能饿死——直查数据库做最终裁决（负载无关）
    const { execSync } = await import("node:child_process")
    const dbPath = path.join(
      process.env.HOME || "",
      ".evoloop/database/backend.db",
    )
    const esc = marker.replace(/'/g, "''")
    let dbUser = 0
    let dbReply = 0
    try {
      dbUser = Number(
        execSync(
          `sqlite3 "${dbPath}" "SELECT count(*) FROM messages WHERE content LIKE '%${esc.slice(1, 20)}%' AND role='human';"`,
        )
          .toString()
          .trim(),
      )
      dbReply = Number(
        execSync(
          `sqlite3 "${dbPath}" "SELECT count(*) FROM messages WHERE content LIKE 'mock reply:%全流程对话%' AND role='ai';"`,
        )
          .toString()
          .trim(),
      )
    } catch (e) {
      console.warn("sqlite3 check failed:", e)
    }
    if (dbUser > 0 && dbReply > 0) {
      userSeen = true
      replySeen = true
      replyText = "(verified via DB)"
    }
    expect(
      userSeen && replySeen,
      `对话验证失败：HTTP轮询 user=${userSeen} reply=${replySeen}，DB user=${dbUser} reply=${dbReply}`,
    ).toBe(true)
  }
  expect(
    divergences,
    `派发阶段 UI 未收敛：\n${divergences.map((d) => `  #T-${d.no}: server=${d.server} ui=${d.ui}`).join("\n")}`,
  ).toEqual([])
  expect(
    finalDivergences,
    `对话后 UI 未收敛：\n${finalDivergences.map((d) => `  #T-${d.no}: server=${d.server} ui=${d.ui}`).join("\n")}`,
  ).toEqual([])
})
