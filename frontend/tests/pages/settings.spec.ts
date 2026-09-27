import { expect, test } from "@playwright/test"
import { expectNoCrash, isAuthed, setupDone } from "./helpers"

test.describe("settings page", () => {
  test.beforeEach(async ({ page }) => {
    test.skip(!isAuthed(), "E2E credentials not configured")
    await page.addInitScript(setupDone)
    await page.goto("/#/settings")
    await expect(page).toHaveURL(/#\/settings$/)
  })

  test("renders page h1 and sidebar tabs", async ({ page }) => {
    await expectNoCrash(page)
    await expect(page.getByRole("heading", { level: 1 })).toBeVisible()
    // Settings tabs are language-agnostic buttons: 常规 / general, 外观 / appearance.
    await expect(
      page.getByRole("button", { name: /general|常规/i }).first(),
    ).toBeVisible()
    await expect(
      page.getByRole("button", { name: /appearance|外观/i }).first(),
    ).toBeVisible()
  })

  test("general tab shows workspace config section", async ({ page }) => {
    await expectNoCrash(page)
    // GeneralSettings renders configuration cards containing inputs.
    await expect(
      page.locator("div[class*='rounded-xl']").first(),
    ).toBeAttached()
    await expect(page.locator("input").first()).toBeVisible()
  })
})
