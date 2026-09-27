import { spawn } from "node:child_process"
import { mkdirSync, writeFileSync } from "node:fs"
import path from "node:path"
import { expect, test } from "@playwright/test"
import { installGlobalProjectMock } from "./duty-isolation"
import {
  fetchServerTruth,
  OBSERVER_BOOTSTRAP,
  parseNo,
  type ServerTask,
  statusTolerant,
} from "./duty-observe-lib"
import { expectNoCrash, isAuthed, setupDone } from "./helpers"

/**
 * 自主值守画布 · 前端运行观测 spec（duty-observe）
 *
 * 动机：后端日志显示任务全部正常完成，但用户在 UI 上"跳几次后卡住不动"。
 * 本 spec 让浏览器自己交代三件事，并逐秒对齐「服务端真相 vs UI 所见」：
 *
 *   1. SSE 通道：/api/v1/stream/tasks 的 EventSource 是否打开、
 *      task_queue_updated 事件是否真的到达页面（包装 EventSource 记账）。
 *   2. UI 心跳：MutationObserver 统计每 500ms DOM 变化量 +
 *      画布卡片状态快照（.dc-card[data-task-id] 的状态类名），
 *      回答"页面还活着吗、哪张卡停在哪一格"。
 *   3. 收敛断言：driver 跑完后，每个任务在 UI 上的最终状态必须等于
 *      服务端 /api/v1/tasks/queue 的最终状态（≤15s 容忍窗），
 *      否则输出逐任务分歧表 —— 这就是"卡住"的可复现证据。
 *
 * 产物（test-results/duty-observe/）：report.md（人读时间线+分歧表）、
 * timeline.json（机器可查）、全程截图序列、Playwright 视频。
 *
 * 驱动：DUTY_DRIVER_CMD 环境变量（shell 命令字符串）。观测就绪后 spawn，
 * 等其退出 + 服务端状态稳定 8s 后做收敛断言。未设置时 spec 纯旁观
 * （观测到状态稳定即收尾，适合对着已在跑的现场做尸检）。
 */

test.use({
  viewport: { width: 1920, height: 1080 },
  video: { mode: "on", size: { width: 1920, height: 1080 } },
})

test.skip(
  !isAuthed(),
  "duty observation requires E2E credentials (frontend/.env)",
)

test("duty canvas observation: UI must converge to server truth", async ({
  page,
}, testInfo) => {
  test.setTimeout(900_000)
  const artifactsDir = path.resolve(process.cwd(), "test-results/duty-observe")
  mkdirSync(artifactsDir, { recursive: true })

  const consoleErrors: string[] = []
  const pageErrors: string[] = []
  const failedRequests: string[] = []
  page.on("console", (msg) => {
    if (msg.type() === "error" && consoleErrors.length < 200) {
      consoleErrors.push(msg.text().slice(0, 300))
    }
  })
  page.on("pageerror", (err) => {
    if (pageErrors.length < 50) pageErrors.push(String(err).slice(0, 400))
  })
  page.on("requestfailed", (req) => {
    if (failedRequests.length < 100) {
      failedRequests.push(
        `${req.method()} ${req.url()} :: ${req.failure()?.errorText}`,
      )
    }
  })

  await page.addInitScript(setupDone)
  await page.addInitScript(OBSERVER_BOOTSTRAP)
  installGlobalProjectMock(page)

  await page.goto("/#/duty-autonomous")
  await expectNoCrash(page)
  await page
    .locator(".dc-card[data-task-id]")
    .first()
    .waitFor({ state: "visible", timeout: 20_000 })
  await page.screenshot({
    path: path.join(artifactsDir, "000-start.png"),
  })

  // 服务端真相基线
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

  // 可选：spawn 演示驱动（重置→喂数→接受提案）
  const driverCmd = process.env.DUTY_DRIVER_CMD
  let driverExit: number | null = null
  if (driverCmd) {
    const child = spawn(driverCmd, { shell: true, stdio: "ignore" })
    child.on("exit", (code) => {
      driverExit = code
    })
  }

  // 观测主循环：服务端每 800ms 一拍，UI 快照由页内采样器 500ms 一拍
  const DEADLINE = Date.now() + (driverCmd ? 600_000 : 90_000)
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
      if (shots < 80 && Date.now() - lastShot > 1_200) {
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
    const driverDone = driverCmd ? driverExit !== null : true
    if (driverDone && Date.now() - lastChange >= STEADY_MS) break
  }

  // 收敛窗：≤45s 让 UI 追平服务端终态。truth 轮询失败必须显性计入
  // （连续失败 = 服务端不可达/连接池挂死，这本身就是"卡住"的证据），
  // 绝不允许当作空队列空洞通过。
  const convergeDeadline = Date.now() + 45_000
  let divergences: {
    no: number
    server: string
    ui: string | "(missing)"
  }[] = []
  let convergeTruthFailures = 0
  let convergeSawTruth = false
  for (;;) {
    let truth: ServerTask[] | null = null
    try {
      truth = await fetchServerTruth(page)
      convergeSawTruth = true
      convergeTruthFailures = 0
    } catch {
      convergeTruthFailures += 1
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
    await page.waitForTimeout(1_000)
  }
  if (!convergeSawTruth) {
    divergences = [
      {
        no: -1,
        server: `UNREACHABLE（收敛窗内 ${convergeTruthFailures} 次 truth 轮询全部失败）`,
        ui: "(unknown)",
      },
    ]
  }

  const obs = await page.evaluate(() => window.__dutyObs)
  await page.screenshot({
    path: path.join(artifactsDir, "999-final.png"),
  })

  // ---------- 报告 ----------
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
  lines.push(`# duty-observe report (${new Date().toISOString()})`)
  lines.push("")
  lines.push(`- driver: ${driverCmd ?? "(none, 纯旁观)"}, exit=${driverExit}`)
  lines.push(`- SSE: open=${sseOpens}, task_queue_updated=${sseEvents}`)
  lines.push(
    `- UI 心跳: ${obs ? obs.mutationTicks.length : 0} 拍中 ${frozenTicks} 拍零 DOM 变化`,
  )
  lines.push(`- 画布连线徽标数（最终）: ${lastEdges}`)
  lines.push(`- truth poll errors: ${pollErrors}`)
  lines.push(
    `- 收敛窗 truth 失败: ${convergeTruthFailures} 次（sawTruth=${convergeSawTruth}）`,
  )
  lines.push(
    `- console errors: ${consoleErrors.length}, pageerrors: ${pageErrors.length}, failed requests: ${failedRequests.length}`,
  )
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
  lines.push("")
  lines.push("## 画布卡片状态快照（UI 所见，状态变化时刻）")
  if (obs) {
    for (const snap of obs.cards) {
      const brief = snap.cards
        .map((c) => `${c.no || c.id.slice(0, 4)}=${c.st}`)
        .join(" ")
      lines.push(`- ${new Date(snap.t).toLocaleTimeString()} ${brief}`)
    }
  }
  if (divergences.length > 0) {
    lines.push("")
    lines.push("## ❌ 收敛失败：UI ≠ 服务端")
    lines.push("")
    lines.push("| 任务 | 服务端终态 | UI 所见 |")
    lines.push("|---|---|---|")
    for (const d of divergences) {
      lines.push(`| #T-${d.no} | ${d.server} | ${d.ui} |`)
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
  if (consoleErrors.length > 0) {
    lines.push("")
    lines.push("## Console errors（前 30 条）")
    for (const e of consoleErrors.slice(0, 30)) lines.push(`- ${e}`)
  }
  if (failedRequests.length > 0) {
    lines.push("")
    lines.push("## Failed requests（前 20 条）")
    for (const e of failedRequests.slice(0, 20)) lines.push(`- ${e}`)
  }
  const report = lines.join("\n")
  writeFileSync(path.join(artifactsDir, "report.md"), report)
  writeFileSync(
    path.join(artifactsDir, "timeline.json"),
    JSON.stringify({ timeline, sse: obs?.sse ?? [], obs }, null, 2),
  )
  await testInfo.attach("report.md", {
    body: report,
    contentType: "text/markdown",
  })

  // ---------- 断言 ----------
  expect(pageErrors, "页面存在未捕获异常").toEqual([])
  if (driverCmd) {
    expect(driverExit, "驱动脚本退出码").toBe(0)
    expect(sseOpens, "SSE 未建立连接").toBeGreaterThan(0)
    expect(sseEvents, "SSE 未收到任何 task_queue_updated 事件").toBeGreaterThan(
      0,
    )
    // SSE churn 回归闸：页面级复用下单轮 ≤10 条连接（此前 ExecutionPanel
    // 逐线程开关，单轮 26+ 条；客户端断连取消 = 连接池孤儿的放大器）
    expect(sseOpens, "SSE 连接数过多（churn 回归）").toBeLessThanOrEqual(10)
  }
  expect(
    divergences,
    `UI 未收敛到服务端终态（卡住实锤）：\n${divergences.map((d) => `  #T-${d.no}: server=${d.server} ui=${d.ui}`).join("\n")}`,
  ).toEqual([])
})
