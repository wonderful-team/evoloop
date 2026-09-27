import { expect, test } from "@playwright/test"
import { expectNoCrash, isAuthed, setupDone } from "./helpers"

test.describe("subscription page", () => {
  test.beforeEach(async ({ page }) => {
    test.skip(!isAuthed(), "E2E credentials not configured")
    await page.addInitScript(setupDone)
    await page.goto("/#/subscription")
    await expect(page).toHaveURL(/#\/subscription$/)
  })

  test("renders plan status dashboard", async ({ page }) => {
    await expectNoCrash(page)
    // Page title is an h2 ("Subscription"), plans section is an h2 too.
    await expect(
      page
        .getByRole("heading", { level: 2 })
        .filter({ hasText: /subscription|订阅/i }),
    ).toBeVisible()
    // Plan comparison + payment method sections.
    await expect(
      page.getByRole("heading", { name: /plan|计划/i }).first(),
    ).toBeVisible()
    await expect(
      page.getByText(/payment|支付|wechat|stripe/i).first(),
    ).toBeVisible()
  })

  test("shows current tier badge", async ({ page }) => {
    await expectNoCrash(page)
    // The active plan badge (flagship tier etc.) renders somewhere.
    await expect(
      page.getByText(/flagship|大师版|tier|等级/i).first(),
    ).toBeVisible()
  })
})
