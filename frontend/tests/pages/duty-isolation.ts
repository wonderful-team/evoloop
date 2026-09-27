/**
 * 值守 E2E 的作用域隔离：后端的"当前项目"（SharedState 持久化）是所有
 * 会话共享的——桌面端/其他浏览器随时会把它拨到他们正在用的项目，值守
 * 看板随之 re-scope 到该项目，测试任务就从画布上消失。
 *
 * 默认用全局视图（project 0）避免多会话污染；可通过环境变量
 * `E2E_DUTY_PROJECT_ID` 指定一个真实项目，让 Agent 在限定项目目录内执行。
 *
 * 路由拦截：
 * - /projects?filter_type=switchable → 返回空列表（无可自动切换的项目）
 * - /projects/switch → 吞掉（不写共享 SharedState，不污染其他会话）
 * - /projects/current → 恒返回 E2E_DUTY_PROJECT_ID（默认 0）
 */
import type { Page } from "@playwright/test"

export const DUTY_PROJECT_ID = process.env.E2E_DUTY_PROJECT_ID || "0"

export function installGlobalProjectMock(page: Page): void {
  const json = (body: unknown) => JSON.stringify(body)

  const testProject =
    Number(DUTY_PROJECT_ID) > 0
      ? {
          project_id: Number(DUTY_PROJECT_ID),
          name: "lead-radar",
          title: "lead-radar",
          description: "E2E duty test project",
          external_path: "/Users/huangjinhuan/Projects/lead-radar",
          path: "/Users/huangjinhuan/Projects/lead-radar",
          local_path: "/Users/huangjinhuan/Projects/lead-radar",
          exists_locally: true,
          local_status: "SYNCED",
          indexing_status: "completed",
        }
      : null

  void page.route("**/api/v1/projects**", (route) => {
    const url = route.request().url()
    if (url.includes("/projects/switch")) {
      return route.fulfill({
        status: 200,
        contentType: "application/json",
        body: json({ ok: true, project_id: Number(DUTY_PROJECT_ID) }),
      })
    }
    if (url.includes("/projects/current")) {
      return route.fulfill({
        status: 200,
        contentType: "application/json",
        body: json({
          code: 0,
          message: "ok",
          data: { project_id: Number(DUTY_PROJECT_ID) },
        }),
      })
    }
    if (url.includes("filter_type=switchable")) {
      const list = testProject ? [testProject] : []
      return route.fulfill({
        status: 200,
        contentType: "application/json",
        body: json({
          code: 0,
          message: "ok",
          data: { list, total: list.length },
        }),
      })
    }
    return route.continue()
  })
}
