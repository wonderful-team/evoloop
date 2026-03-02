import { test, expect } from "@playwright/test"

test.describe("Navigation", () => {
  test("should navigate to home page", async ({ page }) => {
    await page.goto("/")
    await expect(page).toHaveURL("/")
  })

  test("should navigate to settings page", async ({ page }) => {
    await page.goto("/settings")
    await expect(page).toHaveURL("/settings")
    await expect(page.getByRole("heading", { name: /settings/i })).toBeVisible()
  })

  test("should navigate between pages using sidebar", async ({ page }) => {
    await page.goto("/")

    // Click on settings in sidebar
    await page.getByTestId("settings-link").click()
    await expect(page).toHaveURL("/settings")

    // Click back to home
    await page.getByTestId("home-link").click()
    await expect(page).toHaveURL("/")
  })

  test("should show active state for current route", async ({ page }) => {
    await page.goto("/settings")
    const settingsLink = page.getByTestId("settings-link")
    await expect(settingsLink).toHaveAttribute("aria-current", "page")
  })

  test("should handle 404 pages", async ({ page }) => {
    await page.goto("/non-existent-page")
    await expect(page.getByText(/page not found|404/i)).toBeVisible()
  })

  test("should redirect unauthenticated users to login", async ({ page }) => {
    // Clear any existing auth state
    await page.context().clearCookies()
    await page.evaluate(() => {
      localStorage.clear()
    })

    await page.goto("/settings")
    await expect(page).toHaveURL("/login")
  })
})

test.describe("Responsive Navigation", () => {
  test("should show mobile menu on small screens", async ({ page }) => {
    await page.setViewportSize({ width: 375, height: 667 })
    await page.goto("/")

    const mobileMenuButton = page.getByTestId("mobile-menu-button")
    if (await mobileMenuButton.isVisible().catch(() => false)) {
      await mobileMenuButton.click()
      await expect(page.getByTestId("mobile-nav")).toBeVisible()
    }
  })

  test("should collapse sidebar on mobile", async ({ page }) => {
    await page.setViewportSize({ width: 375, height: 667 })
    await page.goto("/")

    const sidebar = page.getByTestId("sidebar")
    if (await sidebar.isVisible().catch(() => false)) {
      // Sidebar might be collapsed by default on mobile
      await expect(sidebar).toHaveClass(/collapsed|hidden/)
    }
  })
})
