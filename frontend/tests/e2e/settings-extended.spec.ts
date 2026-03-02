import { test, expect } from "@playwright/test"
import { SettingsPage } from "../pom/SettingsPage"
import { randomEmail, randomPassword } from "../utils/random"
import { createUser } from "../utils/privateApi"
import { logInUser, logOutUser } from "../utils/user"

test.describe("Extended Settings", () => {
  let settingsPage: SettingsPage

  test.beforeEach(async ({ page }) => {
    settingsPage = new SettingsPage(page)
    await settingsPage.goto()
  })

  test("should display all settings tabs", async () => {
    await expect(settingsPage.profileTab).toBeVisible()
    await expect(settingsPage.passwordTab).toBeVisible()
    await expect(settingsPage.dangerZoneTab).toBeVisible()
  })

  test("should switch between tabs", async () => {
    await settingsPage.goToPasswordTab()
    await expect(settingsPage.page.getByTestId("current-password-input")).toBeVisible()

    await settingsPage.goToProfileTab()
    await expect(settingsPage.page.getByLabel(/full name/i)).toBeVisible()
  })
})

test.describe("Model Settings", () => {
  test.beforeEach(async ({ page }) => {
    await page.goto("/settings/models")
  })

  test("should display model settings", async ({ page }) => {
    await expect(page.getByRole("heading", { name: /model settings/i })).toBeVisible()
  })

  test("should configure LLM provider", async ({ page }) => {
    const providerSelect = page.getByTestId("llm-provider-select")
    if (await providerSelect.isVisible().catch(() => false)) {
      await providerSelect.click()
      await page.getByRole("option", { name: /openai/i }).click()
    }
  })

  test("should save API key", async ({ page }) => {
    const apiKeyInput = page.getByTestId("api-key-input")
    if (await apiKeyInput.isVisible().catch(() => false)) {
      await apiKeyInput.fill("sk-test-key-12345")
      await page.getByRole("button", { name: /save/i }).click()
      await expect(page.getByText(/saved successfully/i)).toBeVisible()
    }
  })
})

test.describe("Embedding Settings", () => {
  test.beforeEach(async ({ page }) => {
    await page.goto("/settings/embeddings")
  })

  test("should display embedding settings", async ({ page }) => {
    await expect(page.getByRole("heading", { name: /embedding/i })).toBeVisible()
  })

  test("should configure embedding model", async ({ page }) => {
    const modelSelect = page.getByTestId("embedding-model-select")
    if (await modelSelect.isVisible().catch(() => false)) {
      await modelSelect.click()
      await page.getByRole("option").first().click()
    }
  })
})

test.describe("MCP Settings", () => {
  test.beforeEach(async ({ page }) => {
    await page.goto("/settings/mcp")
  })

  test("should display MCP manager", async ({ page }) => {
    await expect(page.getByRole("heading", { name: /mcp|model context protocol/i })).toBeVisible()
  })

  test("should add MCP server", async ({ page }) => {
    const addButton = page.getByRole("button", { name: /add server/i })
    if (await addButton.isVisible().catch(() => false)) {
      await addButton.click()
      await expect(page.getByRole("dialog")).toBeVisible()
    }
  })
})

test.describe("Theme Settings", () => {
  let settingsPage: SettingsPage

  test.beforeEach(async ({ page }) => {
    settingsPage = new SettingsPage(page)
    await settingsPage.goto()
  })

  test("should switch to dark mode", async () => {
    await settingsPage.switchTheme("dark")
    await settingsPage.expectTheme("dark")
  })

  test("should switch to light mode", async () => {
    await settingsPage.switchTheme("light")
    await settingsPage.expectTheme("light")
  })

  test("should persist theme preference", async ({ page }) => {
    await settingsPage.switchTheme("dark")

    // Reload and verify theme persists
    await page.reload()
    await page.waitForLoadState("networkidle")

    const isDark = await page.evaluate(() =>
      document.documentElement.classList.contains("dark")
    )
    expect(isDark).toBe(true)
  })
})
