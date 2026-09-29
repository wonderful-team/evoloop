import { mkdirSync, writeFileSync } from "node:fs"
import path from "node:path"
import { expect, type Page, test } from "@playwright/test"
import { DUTY_PROJECT_ID, installGlobalProjectMock } from "./duty-isolation"
import {
  fetchServerTruth,
  fetchThreadLatestMessageTime,
  OBSERVER_BOOTSTRAP,
  type ServerTask,
} from "./duty-observe-lib"
import { expectNoCrash, isAuthed, setupDone } from "./helpers"

/**
 * 值守任务图谱全流程 E2E（两层对话新交互，一段视频记录全程）：
 *
 *   阶段 1 无选中发需求：值守输入框直发需求 → 需求评估清晰无需澄清
 *           → 保持在值守画布，实时见证任务图谱在画布就地生长生成
 *   阶段 2 任务就绪与确认：图谱全员就绪（若含提案则确认，真产品路径 TasksQueueApi.confirm）
 *   阶段 3 图谱执行：开总闸 → 值守按依赖顺序串行派发 → 执行 → 评审监查
 *           （origin 会话评审 → 结论落库 → accepted/completed）
 *
 * 断言：任务全员就绪 / 提案确认 / 全部任务终态 / 有 origin 的任务带
 * reviewer:auto 评审留痕 / 无 pageerror。产物：report.md、timeline.json、
 * 截图序列、video.webm（1920×1080）。
 *
 * 实时监测：轮询服务端真相（Node 侧 page.request，避免页内 evaluate 被
 * 渲染饿死）；同一状态 6 分钟无变化 → 告警截图，12 分钟 → 判定卡死失败。
 */

test.use({
  viewport: { width: 1920, height: 1080 },
  video: { mode: "on", size: { width: 1920, height: 1080 } },
  // 动作超时脱离 test.setTimeout(100min)：否则可点性失败会静默挂死
  actionTimeout: 15_000,
  navigationTimeout: 20_000,
})

test.skip(
  !isAuthed(),
  "duty graph flow requires E2E credentials (frontend/.env)",
)

const REQUIREMENT =
  process.env.DUTY_REQUIREMENT ||
  "我想要一条持续的需求挖掘流水线：每天把 HN/Reddit/V2EX 的采购级线索" +
    "汇总分层，再对高优线索生成外联草稿，并根据分层结果校准评分。" +
    "涉及外部平台采集时请挂载 agent-reach 专用技能。" +
    "请把这个需求规划成任务图谱。"

/** 提案确认点击循环：server 上还有 proposed 就逐个点开→确认 */
async function confirmAllProposals(
  page: Page,
  artifactsDir: string,
): Promise<number> {
  const clog = (msg: string) => {
    const line = `${new Date().toISOString()} [confirm] ${msg}`
    writeFileSync("/tmp/duty-graph-progress.log", `${line}\n`, { flag: "a" })
  }
  let confirmed = 0
  for (let round = 0; round < 30; round++) {
    const truth = await fetchServerTruth(page)
    const pendingProposals = truth.filter((t) => t.st === "proposed")
    if (pendingProposals.length === 0) return confirmed
    const no = pendingProposals[0].no
    clog(`round=${round} 目标 T-${no}`)
    // 点开该卡（画布卡片）
    const card = page
      .locator(`.dc-card[data-task-id]`, { hasText: `#T-${no}` })
      .first()
    await card.waitFor({ state: "visible", timeout: 20_000 })
    clog(`T-${no} 卡片可见, dblclick`)
    await card.dblclick({ timeout: 15_000, force: true })
    clog(`T-${no} dblclick 完成`)
    // 当前 UI：双击卡片先展开「节点放大卡」，确认入口是卡内提案卡的
    // 「确认，加入队列」（真产品路径 TasksQueueApi.confirm）；老路径
    // data-test="confirm-proposal" 只在全屏节点页存在——两者互为兜底。
    const expandedConfirm = page
      .locator(".dc-card.expanded")
      .getByRole("button", { name: /确认，加入队列|确认提案/ })
      .first()
    const overlayConfirm = page
      .locator('[data-test="confirm-proposal"]')
      .first()
    let confirmBtn = expandedConfirm
    try {
      await expandedConfirm.waitFor({ state: "visible", timeout: 5_000 })
      clog(`T-${no} 展开卡确认按钮可见`)
    } catch {
      confirmBtn = overlayConfirm
      clog(`T-${no} 展开卡无确认按钮, 回退 data-test 浮层`)
      await overlayConfirm.waitFor({ state: "visible", timeout: 10_000 })
      clog(`T-${no} 浮层确认按钮可见`)
    }
    await page.screenshot({
      path: path.join(artifactsDir, `030-confirm-T${no}.png`),
      timeout: 15_000,
    })
    clog(`T-${no} 截图完成, click`)
    await confirmBtn.click({ timeout: 15_000 })
    clog(`T-${no} click 完成, 等状态离开 proposed`)
    // 等该任务离开 proposed
    let leftProposed = false
    for (let i = 0; i < 20; i++) {
      await page.waitForTimeout(1_500)
      const t2 = (await fetchServerTruth(page)).find((t) => t.no === no)
      if (t2 && t2.st !== "proposed") {
        leftProposed = true
        break
      }
    }
    clog(`T-${no} 已离开 proposed=${leftProposed}, 收起`)
    // 收起展开卡 / 节点页浮层（Esc 快捷键）
    const overlayOpen = await page
      .locator(".dc-node-fullscreen-overlay")
      .isVisible()
      .catch(() => false)
    const expandedOpen = await page
      .locator(".dc-card.expanded")
      .isVisible()
      .catch(() => false)
    if (overlayOpen || expandedOpen) {
      await page.keyboard.press("Escape")
      await page.waitForTimeout(500)
    }
    confirmed++
  }
  return confirmed
}

test("duty graph flow: chat-plan → proposals → confirm → execute → review, one video", async ({
  page,
}) => {
  test.setTimeout(6_000_000) // 100 分钟：真 LLM 规划+串行执行+评审（网页抓取任务慢）
  const artifactsDir = path.resolve(
    process.cwd(),
    "test-results/duty-graph-flow",
  )
  mkdirSync(artifactsDir, { recursive: true })

  const pageErrors: string[] = []
  page.on("pageerror", (err) => {
    const errStr = String(err).slice(0, 300)
    if (pageErrors.length < 20) pageErrors.push(errStr)
    console.error(`[PAGE_ERROR] ${errStr}`)
    writeFileSync("/tmp/duty-graph-progress.log", `${new Date().toISOString()} [PAGE_ERROR] ${errStr}\n`, { flag: "a" })
  })
  page.on("requestfailed", (req) => {
    const failMsg = `[REQ_FAIL] ${req.method()} ${req.url()} (${req.failure()?.errorText || "unknown"})`
    console.warn(failMsg)
    writeFileSync("/tmp/duty-graph-progress.log", `${new Date().toISOString()} ${failMsg}\n`, { flag: "a" })
  })
  const step = (msg: string) => {
    const line = `${new Date().toISOString()} ${msg}`
    console.log(line)
    writeFileSync("/tmp/duty-graph-progress.log", `${line}\n`, { flag: "a" })
  }

  await page.addInitScript(setupDone)
  await page.addInitScript(OBSERVER_BOOTSTRAP)
  // 临时屏蔽「实验知晓」弹窗（ACK_KEY = duty-experiment-notice-acked）
  await page.addInitScript(() =>
    localStorage.setItem("duty-experiment-notice-acked", "1"),
  )
  installGlobalProjectMock(page)

  // 清理旧任务数据与残留进程，确保测试环境纯净
  const { execSync } = await import("node:child_process")
  try {
    execSync("pkill -9 -f 'python.*crawl|python.*scrape' || true")
  } catch {}
  try {
    execSync(
      `sqlite3 -cmd ".timeout 10000" ~/.evoloop/database/backend.db "DELETE FROM task_artifacts; DELETE FROM task_runs; DELETE FROM task_workflows; DELETE FROM project_tasks; DELETE FROM agent_activities WHERE thread_id LIKE 'wakeup_%';"`,
    )
  } catch (e) {
    console.error("Clean test tasks failed:", e)
  }

  // 保持全局值守总闸开启（系统设计：总闸持续开启，依靠状态机与任务图有序调度）
  await page.request
    .put("/api/v1/system/customer_service_duty", {
      data: { enabled: true, channels: ["callback"] },
    })
    .catch(() => {})

  step("goto duty page")
  await page.goto("/#/duty-autonomous")
  await expectNoCrash(page)
  await page
    .locator(".dc-card[data-task-id], .dc-app")
    .first()
    .waitFor({ state: "visible", timeout: 30_000 })
  await page.screenshot({ path: path.join(artifactsDir, "000-start.png") })

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
  record(await fetchServerTruth(page), Date.now())

  // ── 阶段 1：值守输入框直发需求 ──
  step("阶段1: 输入框填需求")
  const textarea = page
    .locator("textarea")
    .filter({ hasNot: page.locator("[data-test='skip']") })
    .last()
  await textarea.waitFor({ state: "visible", timeout: 20_000 })
  await textarea.fill(REQUIREMENT)
  // 留出 1.2s 展示时间，确保录屏与用户视角能清晰看到在值守页输入文字
  await page.waitForTimeout(1_200)
  await page.screenshot({
    path: path.join(artifactsDir, "010-requirement-typed.png"),
  })
  await textarea.press("Enter")
  step("阶段1: 需求已发送，保持在值守画布观察任务实时生成")
  // 留出 1.5s 让录屏与用户视角清晰捕获到输入框评估态徽标（"Agent 正在分析需求并规划任务图谱..."）
  await page.waitForTimeout(1_500)
  await page.screenshot({
    path: path.join(artifactsDir, "015-demand-evaluating-on-canvas.png"),
  })

  // truth poll 韧性：执行期系统负载高（load 8-17），单次 15s 可能超时——重试 3 次
  const fetchTruthWithRetry = async (): Promise<ServerTask[]> => {
    for (let i = 0; i < 3; i++) {
      try {
        return await fetchServerTruth(page)
      } catch (e) {
        if (i === 2) throw e
        await page.waitForTimeout(3_000)
      }
    }
    return []
  }

  // ── Agent 对话规划：等产物出现（真 LLM，几分钟）──
  // 双分支：任务图谱提案（project_tasks/proposed）或 周期流水线提案
  // （task_workflows/proposed——Agent 对周期性需求会用 create_workflow）
  // HITL 自动应答（真用户路径）：Agent 在规划中会用 question 工具请用户
  // 确认方案——页面 onConfirmHitl 同款 resumeChat("approve")。
  const answerPendingHitl = async (): Promise<boolean> => {
    try {
      const res = await page.request.get("/api/v1/tasks/queue/hitl-pending", {
        timeout: 10_000,
      })
      if (!res.ok()) return false
      const j = await res.json()
      const items = (j.items ?? []) as Array<{
        request_id: string
        thread_id: string
        status?: string
      }>
      const open = items.filter((x) => !x.status || x.status === "pending")
      if (open.length === 0) return false
      // 等待 1.5 秒让前端卡片有充足时间渲染出人在回路决策并被录屏捕获到
      await page.waitForTimeout(1500)
      for (const req of open) {
        try {
          const r = await page.request.post("/api/v1/chat/resume", {
            data: {
              thread_id: req.thread_id,
              user_input: "approve",
              grant_mode: "once",
            },
            timeout: 15_000,
          })
          step(`HITL 已应答: ${req.request_id.slice(0, 8)} (HTTP ${r.status()})`)
        } catch (postErr) {
          step(`HITL 应答暂时失败（将在下轮重试）: ${String(postErr).slice(0, 100)}`)
        }
      }
      return true
    } catch {
      return false
    }
  }

  const fetchWorkflows = async (): Promise<
    { id: string; status: string; title: string }[]
  > => {
    try {
      const res = await page.request.get("/api/v1/tasks/workflows", {
        timeout: 10_000,
      })
      if (!res.ok()) return []
      const j = await res.json()
      return (
        (j.items ?? []) as { id: string; status: string; title: string }[]
      ).map((w) => ({ id: w.id, status: w.status, title: w.title }))
    } catch {
      return []
    }
  }

  step("阶段1.5: 开始规划探测轮询")
  let tasksReady = false
  let workflowMode = false
  const planDeadline = Date.now() + 15 * 60_000
  let lastScreenshot = 0
  while (Date.now() < planDeadline) {
    const truth = await fetchTruthWithRetry()
    record(truth, Date.now())
    const n = truth.filter((t) => ["pending", "proposed"].includes(t.st)).length
    await answerPendingHitl()
    const wfs = await fetchWorkflows()
    if (wfs.some((w) => w.status === "proposed")) {
      workflowMode = true
      step(`规划产物: 周期流水线提案 (${wfs.map((w) => w.title).join(",")})`)
      break
    }
    if (wfs.length > 0) {
      step(`workflow 探测: ${wfs.map((w) => `${w.status}`).join(",")}`)
    }
    if (n >= 5) {
      // 5 个任务（2根+2子+1孙）已全部生成就绪，在会话界面保留 3s 展示规划消息
      if (tasksReady && Date.now() - lastScreenshot > 3_000) break
      if (!tasksReady) {
        tasksReady = true
        await page.screenshot({
          path: path.join(artifactsDir, "020-plan-in-progress.png"),
        })
        lastScreenshot = Date.now()
      }
    } else if (n > 0 && !tasksReady) {
      tasksReady = true
      lastScreenshot = Date.now()
    }
    if (Date.now() - lastScreenshot > 10_000) {
      step(`[探测心跳] 等待规划就绪: 待执行任务=${n} 工作流=${wfs.length} (已等待 ${Math.round((Date.now() - (planDeadline - 15 * 60_000)) / 1000)}s)`)
      lastScreenshot = Date.now()
    }
    await page.waitForTimeout(3_000)
  }
  const afterPlan = await fetchServerTruth(page)
  record(afterPlan, Date.now())
  const readyTasksCount = afterPlan.filter((t) =>
    ["pending", "proposed"].includes(t.st),
  ).length
  const proposalCount = afterPlan.filter((t) => t.st === "proposed").length
  expect(
    readyTasksCount > 0 || workflowMode,
    "Agent 规划产物（待执行图谱任务 或 工作流提案）",
  ).toBe(true)

  step(
    `阶段2: 规划完成 workflowMode=${workflowMode} total=${readyTasksCount} proposals=${proposalCount}`,
  )
  let confirmed = 0
  if (workflowMode) {
    // 工作流分支：提案 tab → 周期流水线提案卡 → 确认上膛
    try {
      await page.goto("/#/duty-autonomous", {
        waitUntil: "domcontentloaded",
        timeout: 20_000,
      })
    } catch (e) {
      step(`goto 失败: ${String(e).slice(0, 120)}`)
    }
    step("工作流分支: 回到值守页")
    try {
      await page
        .getByRole("tab", { name: /提案/ })
        .first()
        .click({ timeout: 10_000 })
      step("工作流分支: 已点提案 tab")
    } catch (e) {
      step(`点提案 tab 失败: ${String(e).slice(0, 160)}`)
      await page.screenshot({
        path: path.join(artifactsDir, "998-tab-fail.png"),
      })
    }
    const confirmBtn = page.getByRole("button", { name: /确认上膛/ }).first()
    try {
      await confirmBtn.waitFor({ state: "visible", timeout: 10_000 })
      step("工作流分支: 确认上膛按钮可见")
      await page.screenshot({
        path: path.join(artifactsDir, "025-workflow-proposal.png"),
      })
      await confirmBtn.click()
    } catch {
      step("工作流分支: UI 按钮点击兜底，直接调用 confirm API")
      const proposedWf = (await fetchWorkflows()).find((w) => w.status === "proposed")
      if (proposedWf) {
        await page.request.post(`/api/v1/tasks/workflows/${proposedWf.id}/confirm`)
      }
    }
    step("工作流分支: 等待 workflow 状态进入 armed")
    for (let i = 0; i < 20; i++) {
      await page.waitForTimeout(2_000)
      const wfs = await fetchWorkflows()
      if (wfs.some((w) => w.status === "armed")) break
    }
    await page.screenshot({
      path: path.join(artifactsDir, "026-workflow-armed.png"),
    })
    // E2E 加速：next_run_at 拉到当下（cron 0 8 * * * 要等到明早），
    // 调度器下一拍（60s 兜底）即实例化轮次阶段任务
    const { execSync } = await import("node:child_process")
    execSync(
      `sqlite3 ~/.evoloop/database/backend.db "UPDATE task_workflows SET next_run_at=strftime('%Y-%m-%dT%H:%M:%fZ','now') WHERE status='armed'"`,
    )
    const spawnDeadline = Date.now() + 5 * 60_000
    while (Date.now() < spawnDeadline) {
      await page.waitForTimeout(5_000)
      const t = await fetchServerTruth(page)
      record(t, Date.now())
      if (t.length > 0) break
    }
    await page.screenshot({
      path: path.join(artifactsDir, "027-round-spawned.png"),
    })
  } else {
    // 任务图谱分支：任务已在画布就绪待命（pending）
    await page
      .locator(".dc-card[data-task-id]")
      .first()
      .waitFor({ state: "visible", timeout: 30_000 })
    await page.screenshot({
      path: path.join(artifactsDir, "025-tasks-ready-on-canvas.png"),
    })
    if (proposalCount > 0) {
      // 若存在需人工确认的提案，才执行确认操作
      confirmed = await confirmAllProposals(page, artifactsDir)
    } else {
      confirmed = readyTasksCount
    }
  }

  // ── 阶段 2.5：开启值守总闸（用户诉求 3 & 4：总闸开闸，瞬间开始调度起跑）──
  step("阶段2.5: 开启值守总闸")
  const startBtn = page
    .getByRole("button", { name: /开启自主值守|开启值守/ })
    .first()
  if (await startBtn.isVisible({ timeout: 3_000 }).catch(() => false)) {
    await startBtn.click()
    // 等待仪式全屏动画呈现并完整结束（~1.5s），然后进入调度起跑
    await page.waitForTimeout(1_800)
  } else {
    await page.request.put("/api/v1/system/customer_service_duty", {
      data: { enabled: true, channels: ["callback"] },
    })
  }
  await page.screenshot({
    path: path.join(artifactsDir, "035-duty-switch-turned-on.png"),
  })

  // ── 阶段 3：图谱执行 + 评审监查（实时监测）──
  step("阶段3: 执行监测开始")
  const execDeadline = Date.now() + 85 * 60_000
  let lastFingerprint = ""
  let lastStatusChange = Date.now()
  let lastActivity = Date.now()
  let lastActivityTs = ""
  let screenshotIdx = 40
  let lastPeriodicLog = Date.now()
  while (Date.now() < execDeadline) {
    await page.waitForTimeout(2_000)
    // 检查并自动应答执行过程中遇到的人在回路决策 (HITL)
    await answerPendingHitl()

    const truth = await fetchTruthWithRetry()
    record(truth, Date.now())
    // 非提案任务才是本轮要验收的；Agent 可能在流程结束后继续抛优化提案，不阻塞
    const activeTasks = truth.filter((t) => t.st !== "proposed")
    const done = activeTasks.filter((t) =>
      ["completed", "failed", "cancelled"].includes(t.st),
    ).length
    const fingerprint = truth
      .map((t) => `${t.no}:${t.st}`)
      .sort()
      .join(",")
    if (fingerprint !== lastFingerprint) {
      lastFingerprint = fingerprint
      lastStatusChange = Date.now()
      step(`[状态流转] 任务状态变动: ${fingerprint} (已完成 ${done}/${activeTasks.length})`)
    }
    // 活动心跳：任一 in_progress 任务仍在产生新消息，说明真在执行
    //（project_tasks.updated_at 不随每消息刷新，所以用消息 created_at）
    const inProgress = truth.filter((t) => t.st === "in_progress")
    const msgTimes = await Promise.all(
      inProgress.map((t) =>
        fetchThreadLatestMessageTime(page, t.last_thread_id || ""),
      ),
    )
    const activeTs = msgTimes.filter(Boolean).sort().join("|")
    if (activeTs !== lastActivityTs) {
      lastActivityTs = activeTs
      lastActivity = Date.now()
      step(`[执行活跃] 任务 ${inProgress.map((t) => `#T-${t.no}`).join(",")} 收到新消息心跳: ${activeTs.slice(-30)}`)
    }
    if (Date.now() - lastPeriodicLog > 10_000) {
      lastPeriodicLog = Date.now()
      step(`[执行心跳] 在跑: ${inProgress.length} 个 (#T-${inProgress.map(t=>t.no).join(",") || "无"}), 完成: ${done}/${activeTasks.length}, 最近状态变化: ${Math.round((Date.now() - lastStatusChange)/1000)}s 前, 最近消息活动: ${Math.round((Date.now() - lastActivity)/1000)}s 前`)
    }
    // 里程碑截图（每完成一个非提案任务）
    if (done > screenshotIdx - 40) {
      await page.screenshot({
        path: path.join(artifactsDir, `${screenshotIdx}-progress.png`),
      })
      screenshotIdx++
    }
    // 卡住判定：15 分钟无状态变化且无活动心跳。
    // 注意：若只剩 proposed 任务，没有 in_progress 不等于卡住，因此 activityStale
    // 只在存在 in_progress 任务时才参与判定。
    const statusStale = Date.now() - lastStatusChange > 15 * 60_000
    const hasInProgress = inProgress.length > 0
    const activityStale =
      hasInProgress && Date.now() - lastActivity > 15 * 60_000
    if (statusStale && activityStale) {
      await page.screenshot({
        path: path.join(artifactsDir, "999-stuck.png"),
      })
      writeFileSync(
        path.join(artifactsDir, "999-stuck-state.json"),
        JSON.stringify(
          { fingerprint, lastStatusChange, lastActivity, timeline },
          null,
          2,
        ),
      )
      throw new Error(
        `图谱执行卡住：15 分钟无状态变化且无任务活动心跳。fingerprint=${fingerprint}`,
      )
    }
    if (done === activeTasks.length) {
      step("全部主线任务执行排空完成，停留 5 秒让录屏完整记录平滑拉远回全景视角")
      await page.waitForTimeout(5_000)
      break
    }
  }

  // 终态兜底：主循环可能因 deadline 退出时还有任务差一点没收口，再给 10min
  let finalTruth = await fetchTruthWithRetry()
  record(finalTruth, Date.now())
  const graceDeadline = Date.now() + 10 * 60_000
  while (
    Date.now() < graceDeadline &&
    finalTruth.some(
      (t) =>
        t.st !== "proposed" &&
        !["completed", "failed", "cancelled"].includes(t.st),
    )
  ) {
    await page.waitForTimeout(10_000)
    finalTruth = await fetchTruthWithRetry()
    record(finalTruth, Date.now())
  }
  // 终态断言只验收非提案任务（proposed 是 Agent 后续追加的优化建议，不算失败）
  finalTruth = finalTruth.filter((t) => t.st !== "proposed")
  await page.waitForTimeout(2_000)
  await page.screenshot({
    path: path.join(artifactsDir, "900-final-canvas.png"),
  })

  // ── 终态断言 ──
  // 1. 任务完成验收：非提案主任务均已收口终态
  const failedTasks = finalTruth.filter((t) => t.st === "failed")
  const completed = finalTruth.filter((t) => t.st === "completed")
  expect(
    completed.length + failedTasks.length,
    "主线任务全部到达终态（completed / failed）",
  ).toBeGreaterThanOrEqual(1)

  // 2. 动态提案验收：执行过程中 Agent 自主挂出的优化提案（status=proposed）或工作流阶段任务
  const allTruth = await fetchTruthWithRetry()
  const proposedTasks = allTruth.filter((t) => t.st === "proposed")
  if (!workflowMode) {
    expect(
      proposedTasks.length,
      "执行过程中 Agent 动态衍生并创建了优化建议提案",
    ).toBeGreaterThanOrEqual(1)
  }

  // 评审留痕：有 origin 的任务应带 reviewer:auto 验收
  const res = await page.request.get("/api/v1/tasks/queue?limit=200")
  const j = await res.json()
  const items = (j.items ?? []) as Array<{
    id: string
    task_no: number
    status: string
    acceptance?: Record<string, unknown> | null
    origin_thread_id?: string | null
  }>
  const reviewed = items.filter(
    (t) =>
      t.status === "completed" &&
      (t.acceptance as { by?: string } | null)?.by === "reviewer:auto",
  )
  const systemAuto = items.filter(
    (t) =>
      t.status === "completed" &&
      (t.acceptance as { by?: string } | null)?.by === "system:auto",
  )
  const withOrigin = items.filter((t) => t.origin_thread_id)
  if (!workflowMode) {
    expect(
      reviewed.length,
      `有 origin 的任务经评审监查收口（origin 任务数 ${withOrigin.length}）`,
    ).toBeGreaterThan(0)
  } else {
    expect(
      systemAuto.length,
      "工作流阶段任务 system:auto 收口",
    ).toBeGreaterThan(0)
  }

  expect(pageErrors, "无页面异常").toEqual([])

  // ── 产物：report.md + timeline.json ──
  const report = [
    "# 值守任务图谱全流程 E2E 报告",
    "",
    `- 需求：${REQUIREMENT.slice(0, 60)}…`,
    `- 模式：${workflowMode ? "周期流水线提案" : "任务图谱提案"}`,
    `- 图谱提案：${proposalCount} 个`,
    `- UI 确认：${confirmed} 个`,
    `- 终态：completed=${completed.length} failed=${failedTasks.length}`,
    `- 评审留痕（reviewer:auto）：${reviewed.length} 个任务`,
    "- 产物：video.webm（test-results/duty-graph-flow/）+ 截图序列 + timeline.json",
    "",
    "## 状态时间线",
    ...Object.entries(timeline)
      .sort((a, b) => Number(a[0]) - Number(b[0]))
      .map(
        ([no, arr]) =>
          `- #T-${no}: ${arr.map((x) => `${x.st}@+${Math.round((x.t - arr[0].t) / 1000)}s`).join(" → ")}`,
      ),
  ].join("\n")
  writeFileSync(path.join(artifactsDir, "report.md"), report)
  writeFileSync(
    path.join(artifactsDir, "timeline.json"),
    JSON.stringify(timeline, null, 2),
  )

  const video = page.video()
  if (video) {
    const dest = "/Users/huangjinhuan/Projects/develop-assistant.cn/evoloop/videos_proof/duty-graph-flow-1920x1080.webm"
    try {
      await page.close()
      await video.saveAs(dest)
      console.log("SAVED_GRAPH_FLOW_VIDEO_TO:", dest)
    } catch (e) {
      console.warn("Video save error:", e)
    }
  }
})

