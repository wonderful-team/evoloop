import { expect, test } from "@playwright/test"
import { expectNoCrash, isAuthed, setupDone } from "./helpers"

test.describe("learning center", () => {
  test("learning hub renders title and tabs", async ({ page }) => {
    test.skip(!isAuthed(), "E2E credentials not configured")
    await page.addInitScript(setupDone)
    await page.goto("/#/learning")
    await expect(page).toHaveURL(/#\/learning$/)
    await expectNoCrash(page)
    await expect(
      page
        .getByRole("heading", { level: 1 })
        .filter({ hasText: /learning|学习/i }),
    ).toBeVisible()
  })

  test("skill edit page renders editor shell", async ({ page }) => {
    test.skip(!isAuthed(), "E2E credentials not configured")
    await page.addInitScript(setupDone)
    await page.goto("/#/learning/skills/demo-skill/edit")
    await page.waitForLoadState("domcontentloaded")
    await expectNoCrash(page)
  })

  test("macro edit page renders editor shell", async ({ page }) => {
    test.skip(!isAuthed(), "E2E credentials not configured")
    await page.addInitScript(setupDone)
    await page.goto("/#/learning/macros/demo-macro/edit")
    await page.waitForLoadState("domcontentloaded")
    await expectNoCrash(page)
  })
})
