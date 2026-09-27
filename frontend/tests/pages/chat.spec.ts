import { expect, test } from "@playwright/test"
import { expectNoCrash, setupDone } from "./helpers"

/**
 * Chat page — the main app workspace. Rendered inside the `_layout` shell
 * (sidebar + header). Login state is optional (guest shell renders too).
 */
test.describe("chat page", () => {
  test.beforeEach(async ({ page }) => {
    await page.addInitScript(setupDone)
  })

  test("chat route renders the workspace shell", async ({ page }) => {
    await page.goto("/#/chat")
    await expect(page).toHaveURL(/#\/chat$/)
    await expectNoCrash(page)
  })

  test("sidebar navigation is present", async ({ page }) => {
    await page.goto("/#/chat")
    await expect(page.locator('[data-tour="sidebar-chat"]')).toBeVisible()
    await expect(page.locator('[data-tour="sidebar-projects"]')).toBeVisible()
    // todo 域已退役：侧边栏不得再有待办入口
    await expect(page.locator('[data-tour="sidebar-todos"]')).toHaveCount(0)
  })

  test("main chat area renders a composer or welcome state", async ({
    page,
  }) => {
    await page.goto("/#/chat")
    await expectNoCrash(page)
    // Either a message list with a composer, or the welcome panel.
    const composer = page.locator("textarea")
    const messages = page.locator('[data-tour="chat-messages"]')
    await expect(composer.or(messages).first()).toBeVisible({ timeout: 10_000 })
  })
})
