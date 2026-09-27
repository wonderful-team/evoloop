import { expect, test, type Page } from "@playwright/test"

/**
 * 项目切换 · 会话归属前端契约 spec（修复验证）
 *
 * 背景：切到"工作空间"(global, project_id=0) 后发消息，会话仍归属上一个
 * 项目——根因是三层 falsy-0 陷阱（ProjectSwitcher 不为 0 同步 SSOT /
 * threadId 不随项目切换重置）。
 *
 * 本 spec 在网络层断言前端契约（不依赖后端真实数据，全部 mock）：
 *   A. 切到工作空间 → POST /projects/switch 请求体 project_id === 0
 *   B. 切换后发消息 → POST /chat 请求体 project_id === 0 且不带旧 thread_id
 *   C. 切回项目 → switch(120) + 后续消息 project_id === 120（双向）
 */

const MOCK_PROJECTS = {
  list: [
    {
      // global(0) 必须在列表中：projectStore 启动/打开切换器时会用后端
      // 列表对账 localStorage 最近选择，缺 0 会把工作空间踢回 firstLocal。
      id: 0,
      name: "global",
      description: "mock global workspace",
      path: "",
      exists_locally: false,
    },
    {
      id: 120,
      name: "mall-backend",
      description: "mock mall project",
      path: "/mock/mall-backend",
      exists_locally: true,
    },
    {
      id: 121,
      name: "another-project",
      description: "mock another",
      path: "/mock/another",
      exists_locally: true,
    },
  ],
}

// 注意：projectStore 启动会用后端列表对账 localStorage 的最近选择——
// mock 列表必须包含使用到的每一个 project_id（含 global 的 0，
// GLOBAL_PROJECT 由前端常量提供，对账只查 id 存在性）。

test.describe("项目切换 · 会话归属前端契约", () => {
  let switchCalls: Array<Record<string, unknown>> = []
  let chatCalls: Array<Record<string, unknown>> = []

  async function installMocks(page: Page) {
    switchCalls = []
    chatCalls = []

    // 项目列表（switchable 对话框数据源）
    await page.route("**/api/v1/projects**", async (route) => {
      if (route.request().method() === "GET") {
        await route.fulfill({
          contentType: "application/json",
          body: JSON.stringify({ list: MOCK_PROJECTS.list, total: 2 }),
        })
        return
      }
      await route.fulfill({ status: 200, body: "{}", contentType: "application/json" })
    })

    // 项目切换（核心断言目标）
    await page.route("**/api/v1/projects/switch", async (route) => {
      switchCalls.push(JSON.parse(route.request().postData() || "{}"))
      await route.fulfill({
        contentType: "application/json",
        body: JSON.stringify({ ok: true, project_id: 0 }),
      })
    })

    // 发消息（归属断言目标）
    await page.route("**/api/v1/chat", async (route) => {
      if (route.request().method() === "POST") {
        chatCalls.push(JSON.parse(route.request().postData() || "{}"))
        await route.fulfill({
          contentType: "application/json",
          body: JSON.stringify({
            status: "queued",
            thread_id: "mock-thread-id",
            message_id: "mock-msg-id",
          }),
        })
        return
      }
      await route.fulfill({ status: 200, body: "{}", contentType: "application/json" })
    })

    // SSE 读通道：保持连接但不推送（fulfill 单响应，EventSource 自动重连）
    await page.route("**/api/v1/stream/chat/**", (route) =>
      route.fulfill({
        contentType: "text/event-stream",
        body: ": ping\n\n",
      }),
    )
    // 其余查询统一静默（历史/活动/任务/changeset/技能等）
    await page.route("**/api/v1/**", async (route) => {
      const url = route.request().url()
      if (
        url.includes("/projects") ||
        url.includes("/chat") ||
        url.includes("/stream/")
      ) {
        return route.fallback()
      }
      await route.fulfill({
        contentType: "application/json",
        body: JSON.stringify({ data: [], list: [], total: 0 }),
      })
    })


  }

  test("切到工作空间：switch(0) 同步 + 发消息归属 0 且开新会话", async ({
    page,
  }) => {
    await installMocks(page)

    // 初始项目=120（localStorage 持久化的最近选择）
    await page.addInitScript(() => {
      localStorage.setItem("evoloop_last_project_id", "120")
      localStorage.setItem("evoloop-guest-id", "e2e-guest")
      localStorage.setItem("evoloop_setup_completed", "true")
    })
    await page.goto("/#/chat")

    const trigger = page.locator('[role="combobox"]').first()
    await expect(trigger).toBeVisible({ timeout: 15_000 })
    // 初始显示 mall-backend（120）
    await expect(trigger).toContainText("mall-backend", { timeout: 15_000 })

    // 打开切换器 → 选择 global 卡片（en 环境 i18n 文案为 "Workspace"；
    // 卡片标题按语言渲染，故用 heading 角色而非硬编码中文）
    await trigger.click()
    const globalCard = page
      .getByRole("heading", { name: /workspace|工作空间/i })
      .first()
    await expect(globalCard).toBeVisible({ timeout: 10_000 })
    await globalCard.click()

    // 断言 A：switch(0) 请求发出（修复点：此前 0 被 falsy 挡住）
    await expect
      .poll(() => switchCalls, { timeout: 10_000 })
      .toContainEqual(expect.objectContaining({ project_id: 0 }))

    // 触发器文案切换为 global 态（en: Workspace）
    await expect(trigger).toContainText(/Workspace|工作空间/i, {
      timeout: 10_000,
    })

    // 发消息（新会话）
    const composer = page.locator("textarea").first()
    await expect(composer).toBeVisible({ timeout: 10_000 })
    await composer.fill("生成一匹真的马")
    await composer.press("Enter")

    // 断言 B：POST /chat 归属工作空间 + 开新会话（不带旧 thread_id）
    await expect
      .poll(() => chatCalls.length, { timeout: 15_000 })
      .toBeGreaterThan(0)
    const body = chatCalls[chatCalls.length - 1]
    expect(body.project_id).toBe(0)
    expect(body.thread_id).toBeUndefined()
  })

  test("切回项目：switch(120) + 消息归属 120（双向）", async ({ page }) => {
    await installMocks(page)

    // 初始即工作空间
    await page.addInitScript(() => {
      localStorage.setItem("evoloop_last_project_id", "0")
      localStorage.setItem("evoloop-guest-id", "e2e-guest")
      localStorage.setItem("evoloop_setup_completed", "true")
    })
    await page.goto("/#/chat")

    const trigger = page.locator('[role="combobox"]').first()
    await expect(trigger).toBeVisible({ timeout: 15_000 })
    await expect(trigger).toContainText(/Workspace|工作空间/i, {
      timeout: 15_000,
    })

    // 切回 mall-backend
    await trigger.click()
    const mallCard = page.locator("text=mall-backend").first()
    await expect(mallCard).toBeVisible({ timeout: 10_000 })
    await mallCard.click()

    await expect
      .poll(() => switchCalls, { timeout: 10_000 })
      .toContainEqual(expect.objectContaining({ project_id: 120 }))

    const composer = page.locator("textarea").first()
    await expect(composer).toBeVisible({ timeout: 10_000 })
    await composer.fill("查询订单")
    await composer.press("Enter")

    await expect
      .poll(() => chatCalls.length, { timeout: 15_000 })
      .toBeGreaterThan(0)
    const body = chatCalls[chatCalls.length - 1]
    expect(body.project_id).toBe(120)
    expect(body.thread_id).toBeUndefined()
  })
})
