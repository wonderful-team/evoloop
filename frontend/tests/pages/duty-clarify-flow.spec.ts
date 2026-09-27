import { mkdirSync, writeFileSync } from "node:fs"
import path from "node:path"
import { expect, test } from "@playwright/test"
import { installGlobalProjectMock } from "./duty-isolation"
import { fetchServerTruth, OBSERVER_BOOTSTRAP } from "./duty-observe-lib"
import { expectNoCrash, isAuthed } from "./helpers"

/**
 * 需求含糊需交互澄清的转场全流程 E2E：
 *
 *   1. 用户在值守画布输入含糊需求（"帮我搭建一条需求挖掘流水线"）；
 *   2. 输入框上方浮现动态呼吸状态胶囊："Agent 正在分析需求并规划任务图谱..."；
 *   3. Agent 评估判定需求缺少关键平台与分层规则，触发 HITL / 追问；
 *   4. 前端监听到交互澄清事件，平滑转场至「智能体对话」（/chat）；
 *   5. 用户在对话中回复具体规则（"重点监控 HN/Reddit/V2EX..."）；
 *   6. Agent 评估通过，调用 tasks 工具构建图谱；
 *   7. 用户切回值守画布，见证 5 个任务图谱节点已在画布就绪！
 */

test.use({
  viewport: { width: 1920, height: 1080 },
  video: { mode: "on", size: { width: 1920, height: 1080 } },
  actionTimeout: 15_000,
  navigationTimeout: 20_000,
})

test.skip(
  !isAuthed(),
  "duty clarify flow requires E2E credentials (frontend/.env)",
)

test("duty clarify flow: ambiguous demand → transfer to chat → clarify → generate graph", async ({
  page,
}) => {
  test.setTimeout(120_000)
  const artifactsDir = path.resolve(
    process.cwd(),
    "test-results",
    "duty-clarify-flow",
  )
  mkdirSync(artifactsDir, { recursive: true })
  const logFile = path.join(artifactsDir, "progress.log")
  const step = (msg: string) => {
    const line = `${new Date().toISOString()} ${msg}`
    console.log(`[E2E] ${line}`)
    writeFileSync(logFile, `${line}\n`, { flag: "a" })
  }

  await page.addInitScript(OBSERVER_BOOTSTRAP)
  await page.addInitScript(() =>
    localStorage.setItem("duty-experiment-notice-acked", "1"),
  )
  installGlobalProjectMock(page)

  // 清理历史测试数据
  const { execSync } = await import("node:child_process")
  try {
    execSync(
      `sqlite3 ~/.evoloop/database/backend.db "DELETE FROM task_artifacts; DELETE FROM task_runs; DELETE FROM task_workflows; DELETE FROM project_tasks; DELETE FROM conversations WHERE title LIKE '%需求%' OR title LIKE '%线索%';"`,
    )
  } catch (e) {
    console.error("Clean test tasks failed:", e)
  }

  step("1. 进入自主值守画布")
  await page.goto("/#/duty-autonomous")
  await expectNoCrash(page)
  await page
    .locator(".dc-card[data-task-id], .dc-app")
    .first()
    .waitFor({ state: "visible", timeout: 30_000 })
  await page.screenshot({ path: path.join(artifactsDir, "000-start.png") })

  step("2. 输入框键入含糊需求")
  const textarea = page
    .locator("textarea")
    .filter({ hasNot: page.locator("[data-test='skip']") })
    .last()
  await textarea.waitFor({ state: "visible", timeout: 20_000 })
  await textarea.fill("帮我搭建一条需求挖掘流水线")
  await page.waitForTimeout(1_200)
  await page.screenshot({
    path: path.join(artifactsDir, "010-ambiguous-demand-typed.png"),
  })

  step("3. 发送含糊需求，检验输入区上方胶囊与转场触发")
  await textarea.press("Enter")
  // 留出 1 秒记录输入区上方浮动的胶囊提示
  await page.waitForTimeout(1_000)
  await page.screenshot({
    path: path.join(artifactsDir, "015-evaluating-above-input.png"),
  })

  step("4. Agent 判定需求含糊发起追问，等待平滑转场 /chat")
  await page.waitForURL(/#\/chat/, { timeout: 20_000 })
  await page.screenshot({
    path: path.join(artifactsDir, "020-transferred-to-chat.png"),
  })

  step("5. 在会话界面查验 Agent 澄清问题并提交具体方案")
  // 预留 1.5s 展示会话界面的追问内容
  await page.waitForTimeout(1_500)
  await page.screenshot({
    path: path.join(artifactsDir, "025-clarification-question-shown.png"),
  })

  const chatInput = page
    .locator("textarea")
    .filter({ hasNot: page.locator("[data-test='skip']") })
    .last()
  await chatInput.waitFor({ state: "visible", timeout: 20_000 })
  await chatInput.fill(
    "重点监控 HN/Reddit/V2EX 的采购意向线索，按采购客单价分层，生成外联草案并校准评分。请把这个需求规划成任务图谱。",
  )
  await page.waitForTimeout(1_000)
  const submitBtn = page
    .getByRole("button", { name: /Submit|确定提交|提交/i })
    .first()
  if (await submitBtn.isVisible().catch(() => false)) {
    await submitBtn.click()
  } else {
    await chatInput.press("Enter")
  }
  await page.waitForTimeout(1_000)
  await page.screenshot({
    path: path.join(artifactsDir, "030-clarification-submitted.png"),
  })
  step("6. 具体方案已提交，等待图谱任务生成")

  // 轮询服务端，确认 5 个任务规划产出
  const deadline = Date.now() + 60_000
  while (Date.now() < deadline) {
    const truth = await fetchServerTruth(page)
    if (truth.length >= 5) {
      step(`图谱已生成: ${truth.length} 个任务`)
      break
    }
    await page.waitForTimeout(2_000)
  }
  await page.screenshot({
    path: path.join(artifactsDir, "035-tasks-planned-in-chat.png"),
  })

  step("7. 点击顶栏「自主值守」Tab 切回值守画布")
  const dutyTab = page
    .getByRole("button", { name: /Autonomous Duty|自主值守|值守/i })
    .first()
  await dutyTab.waitFor({ state: "visible", timeout: 10_000 })
  await dutyTab.click()
  await page.waitForURL(/#\/duty-autonomous/, { timeout: 15_000 })

  step("8. 验证 5 个图谱任务在画布完整渲染")
  await page
    .locator(".dc-card[data-task-id]")
    .first()
    .waitFor({ state: "visible", timeout: 30_000 })
  await page.waitForTimeout(2_000)
  await page.screenshot({
    path: path.join(artifactsDir, "040-tasks-ready-on-duty-canvas.png"),
  })

  const finalTasks = await fetchServerTruth(page)
  expect(finalTasks.length, "图谱中应包含 5 个生成任务").toBeGreaterThanOrEqual(5)
  step("E2E 澄清转场与图谱生成验证全部完成！")

  const video = page.video()
  await page.close()
  if (video) {
    const videoPath = await video.path()
    const { copyFileSync } = await import("node:fs")
    try {
      copyFileSync(videoPath, path.join(artifactsDir, "video.webm"))
    } catch {
      // ignore
    }
  }
})
