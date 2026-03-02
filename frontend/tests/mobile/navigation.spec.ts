import { test, expect } from "@playwright/test"

test.describe("Mobile Navigation", () => {
  test.beforeEach(async ({ page }) => {
    // Set mobile viewport
    await page.setViewportSize({ width: 375, height: 667 })
  })

  test("should display mobile tab bar", async ({ page }) => {
    await page.goto("/")
    await expect(page.getByTestId("mobile-tab-bar")).toBeVisible()
  })

  test("should navigate between tabs", async ({ page }) => {
    await page.goto("/")

    // Navigate to Projects tab
    await page.getByTestId("tab-projects").click()
    await expect(page).toHaveURL(/\/projects/)

    // Navigate to Devices tab
    await page.getByTestId("tab-devices").click()
    await expect(page).toHaveURL(/\/devices/)

    // Navigate to Profile tab
    await page.getByTestId("tab-profile").click()
    await expect(page).toHaveURL(/\/profile/)
  })

  test("should show active tab state", async ({ page }) => {
    await page.goto("/projects")

    const projectsTab = page.getByTestId("tab-projects")
    await expect(projectsTab).toHaveAttribute("aria-selected", "true")
  })
})

test.describe("Mobile Chat Interface", () => {
  test.beforeEach(async ({ page }) => {
    await page.setViewportSize({ width: 375, height: 667 })
    await page.goto("/chat")
  })

  test("should display mobile chat layout", async ({ page }) => {
    await expect(page.getByTestId("mobile-chat-screen")).toBeVisible()
    await expect(page.getByTestId("chat-input")).toBeVisible()
  })

  test("should send message from mobile", async ({ page }) => {
    const messageInput = page.getByTestId("chat-input")
    await messageInput.fill("Hello from mobile")
    await page.getByTestId("send-button").click()

    await expect(page.getByText("Hello from mobile")).toBeVisible()
  })

  test("should handle voice input button", async ({ page }) => {
    const voiceButton = page.getByTestId("voice-input-button")
    if (await voiceButton.isVisible().catch(() => false)) {
      await voiceButton.click()
      await expect(page.getByTestId("voice-recording-overlay")).toBeVisible()
    }
  })
})

test.describe("Mobile Auth Flow", () => {
  test.beforeEach(async ({ page }) => {
    await page.setViewportSize({ width: 375, height: 667 })
  })

  test("should display mobile login screen", async ({ page }) => {
    await page.goto("/login")
    await expect(page.getByTestId("mobile-login-screen")).toBeVisible()
  })

  test("should login on mobile", async ({ page }) => {
    await page.goto("/login")

    await page.getByTestId("username-input").fill("testuser")
    await page.getByTestId("password-input").fill("password123")
    await page.getByRole("button", { name: /log in/i }).click()

    // Should redirect to home after successful login
    await page.waitForURL("/")
  })
})
