import { expect, test } from "@playwright/test"
import { expectNoCrash, setupDone } from "./helpers"

/**
 * Public (pre-auth) pages — visible to guests, no login required.
 * Rendered with a guest storage state so redirect-on-auth never kicks in.
 */
test.describe("public auth pages", () => {
  test.use({ storageState: { cookies: [], origins: [] } })
  test.beforeEach(async ({ page }) => {
    await page.addInitScript(setupDone)
  })

  test("login renders the auth form", async ({ page }) => {
    await page.goto("/#/login")
    await expect(page).toHaveURL(/#\/login$/)
    await expect(page.locator("form")).toBeVisible()
    await expect(page.getByTestId("email-input")).toBeVisible()
    await expect(page.getByTestId("password-input")).toBeVisible()
    await expectNoCrash(page)
  })

  test("signup renders the auth form", async ({ page }) => {
    await page.goto("/#/signup")
    await expect(page).toHaveURL(/#\/signup$/)
    await expect(page.locator("form")).toBeVisible()
    await expectNoCrash(page)
  })

  test("recover-password renders the request form", async ({ page }) => {
    await page.goto("/#/recover-password")
    await expect(page).toHaveURL(/#\/recover-password$/)
    await expect(page.locator("form")).toBeVisible()
    await expectNoCrash(page)
  })

  test("reset-password requires a token query param", async ({ page }) => {
    // Without ?token= the route redirects guests to /login.
    await page.goto("/#/reset-password")
    await expect(page).toHaveURL(/#\/login$/)
    await expectNoCrash(page)
  })

  test("reset-password form renders with a token", async ({ page }) => {
    await page.goto("/#/reset-password?token=test-token")
    await expect(page).toHaveURL(/#\/reset-password/)
    await expect(page.locator("form")).toBeVisible()
    await expectNoCrash(page)
  })
})

/**
 * Overlay / HUD routes — rendered without the app shell (Tauri overlay
 * surface). Only assert they load without the crash boundary.
 */
test.describe("overlay routes", () => {
  for (const [name, path] of [
    ["marker-overlay", "/marker-overlay"],
    ["android-marker-overlay", "/android-marker-overlay"],
    ["voice-hud", "/voice-hud"],
  ] as const) {
    test(`${name} renders (${path})`, async ({ page }) => {
      await page.goto(`/#${path}`)
      await page.waitForLoadState("domcontentloaded")
      await expectNoCrash(page)
    })
  }
})
