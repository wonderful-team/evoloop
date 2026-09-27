import { expect, test } from "@playwright/test"

/**
 * Smoke tests — validate the app boots and public routes render.
 * These run against the dev server (http://localhost:5173) which proxies to
 * the backend; no login credentials are required.
 */
const emptyState = { cookies: [], origins: [] }

test.describe("app boot smoke", () => {
  // These tests target the public, pre-auth login page — always run them in a
  // guest context regardless of E2E credentials.
  test.use({ storageState: emptyState })
  test("login page renders the auth form", async ({ page }) => {
    await page.goto("/#/login")
    await expect(page).toHaveURL(/#\/login$/)
    await expect(page.locator("form")).toBeVisible()
  })

  test("username / password inputs are present on login", async ({ page }) => {
    await page.goto("/#/login")
    await expect(
      page.getByPlaceholder(/username|邮箱|用户名|账号/i),
    ).toBeVisible()
    await expect(page.getByPlaceholder(/password|密码/i)).toBeVisible()
  })

  test("empty submit surfaces validation errors", async ({ page }) => {
    await page.goto("/#/login")
    await page.locator("form button[type='submit']").click()
    // react-hook-form + zod renders a <FormMessage> / <p> error on both fields.
    await expect(page.locator("form p").first()).toBeVisible()
  })
})
