import { test as setup } from "@playwright/test"

/**
 * Auth setup project.
 *
 * The chromium project declares a dependency on this setup and uses
 * `storageState: 'playwright/.auth/user.json'`.
 *
 * When `E2E_USERNAME` / `E2E_PASSWORD` are present in the environment (see
 * the gitignored `frontend/.env`), the setup performs a real login against the
 * running dev stack so every page test runs with an authenticated session.
 * Otherwise it persists an empty bucket and the authenticated-only specs skip.
 */
const authFile = "playwright/.auth/user.json"

const username = process.env.E2E_USERNAME
const password = process.env.E2E_PASSWORD

setup(
  "authenticate (empty storage for public-route tests)",
  async ({ page }) => {
    await page.goto("/#/login")
    await page.waitForURL("**/#/login")

    if (username && password) {
      await page.getByTestId("email-input").fill(username)
      await page.getByTestId("password-input").fill(password)
      await page.locator("form button[type='submit']").click()
      // Successful login navigates away from /login (redirect to "/#/chat").
      await page.waitForURL((url) => !url.hash.includes("/login"), {
        timeout: 30_000,
      })
    }

    await page.context().storageState({ path: authFile })
  },
)
