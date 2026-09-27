// E2E：执行结束 → 展开的节点页自动收缩回卡片
// 时序：先展开 pending 任务节点页（模拟用户正在看）→ 触发执行 →
// mock 场景推进到终态 → SSE task_advanced → 节点页自动收缩

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

  // 找 task 16 的卡片 id 并先展开（用户正看着这个节点页）
  const cardId = await page.evaluate(() => {
    const res = fetch("/api/v1/tasks/queue?limit=200", {
      credentials: "include",
    })
      .then((r) => r.json())
      .then((j) => {
        const items = (j.items ?? j.data?.items ?? []) as {
          id: string
          task_no: number
        }[]
        const t16 = items.find((t) => t.task_no === 4)
        return t16 ? t16.id : ""
      })
    return res
  })
  expect(cardId, "task 4 not found").toBeTruthy()
  await page.locator(`.dc-card[data-task-id="${cardId}"]`).first().dblclick()
  await page
    .locator(`.dc-card[data-task-id="${cardId}"].expanded`)
    .waitFor({ state: "visible", timeout: 10_000 })

  // 触发"执行结束"事件：走 API accept（waiting_acceptance → completed），
  // 事件由 API 进程发布（浏览器订阅的就是它）——确定性触发
  await page.evaluate(async (tid: string) => {
    const res = await fetch(`/api/v1/tasks/queue/${tid}/accept`, {
      method: "POST",
      credentials: "include",
    })
    if (!res.ok) throw new Error(`accept failed: ${res.status}`)
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
})
