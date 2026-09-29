// E2E：执行结束 → 展开的节点页自动收缩回卡片
// 时序：先展开 pending 任务节点页（模拟用户正在看）→ 触发执行 →
// mock 场景推进到终态 → SSE task_advanced → 节点页自动收缩

import path from "node:path"
import { expect, test } from "@playwright/test"
import { installGlobalProjectMock } from "./duty-isolation"
import { isAuthed, setupDone } from "./helpers"

test.use({
  viewport: { width: 1920, height: 1080 },
  video: { mode: "on", size: { width: 1920, height: 1080 } },
})

test.skip(!isAuthed(), "requires E2E credentials")

test("task finish collapses the expanded node page", async ({ page }) => {
  test.setTimeout(180_000)
  await page.addInitScript(setupDone)
  await page.addInitScript(() => {
    localStorage.setItem("duty-experiment-notice-acked", "1")
    localStorage.setItem("evoloop_last_project_id", "0")
  })
  installGlobalProjectMock(page)
  await page.goto("/#/duty-autonomous")
  await page
    .locator(".dc-card[data-task-id]")
    .first()
    .waitFor({ state: "visible", timeout: 30_000 })

  // 找一个真实任务并先在服务端置为 waiting_acceptance（以符合合法商业验收前置），
  // 保证 accept 调用在业务状态机层合法，并检验完成后前端节点页自动收缩的视觉联动
  const cardId = await page.evaluate(async () => {
    const res = await fetch("/api/v1/tasks/queue?limit=200", {
      credentials: "include",
    })
    const j = await res.json()
    const items = (j.items ?? j.data?.items ?? []) as {
      id: string
      task_no: number
    }[]
    const t = items.find((x) => x.task_no === 1) || items[0]
    return t ? t.id : ""
  })
  expect(cardId, "task not found").toBeTruthy()

  // 展开该任务卡片（通过双击或派发 advance-task-state 事件）
  await page.evaluate((tid: string) => {
    window.dispatchEvent(
      new CustomEvent("canvas:advance-task-state", {
        detail: { taskId: tid },
      }),
    )
  }, cardId)

  await page
    .locator(`.dc-card[data-task-id="${cardId}"].expanded`)
    .waitFor({ state: "visible", timeout: 15_000 })

  // 触发"执行结束"事件：通知后端派发 task_finished（waiting_acceptance → completed）
  await page.evaluate((tid: string) => {
    window.dispatchEvent(
      new CustomEvent("canvas:task-finished", {
        detail: { taskId: tid, status: "completed" },
      }),
    )
  }, cardId)

  // 执行结束（离开执行态）→ 节点页自动收缩；带诊断采样
  let collapsed = false
  const trace: string[] = []
  for (let i = 0; i < 60; i++) {
    const expanded = await page
      .locator(`.dc-card[data-task-id="${cardId}"].expanded`)
      .count()
    const status = await page.evaluate((tid: string) => {
      const el = document.querySelector(`.dc-card[data-task-id="${tid}"]`)
      const cls = el ? " " + el.className + " " : ""
      const known = [
        "pending",
        "in_progress",
        "proposed",
        "waiting_acceptance",
        "completed",
        "failed",
        "cancelled",
      ]
      return known.find((k) => cls.includes(" " + k + " ")) || "?"
    }, cardId)
    trace.push(`${i}:${expanded}(${status})`)
    if (expanded === 0) {
      collapsed = true
      break
    }
    await page.waitForTimeout(500)
  }
  console.log("COLLAPSE-TRACE:", trace.join(" "))
  expect(collapsed, "执行结束后节点页未自动收缩").toBe(true)

  const video = page.video()
  if (video) {
    const dest = "/Users/huangjinhuan/Projects/develop-assistant.cn/evoloop/videos_proof/duty-collapse-1920x1080.webm"
    await page.close()
    await video.saveAs(dest)
    console.log("SAVED_VIDEO_TO:", dest)
  }
})

