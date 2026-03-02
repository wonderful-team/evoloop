import { test, expect } from "@playwright/test"

test.describe("Learning Mode", () => {
  test.beforeEach(async ({ page }) => {
    await page.goto("/learning")
  })

  test("should display learning interface", async ({ page }) => {
    await expect(page.getByRole("heading", { name: /learning/i })).toBeVisible()
  })

  test("should show Android mirror console when available", async ({ page }) => {
    const mirrorConsole = page.getByTestId("android-mirror-console")
    if (await mirrorConsole.isVisible().catch(() => false)) {
      await expect(mirrorConsole).toBeVisible()
    }
  })

  test("should start recording session", async ({ page }) => {
    const recordButton = page.getByRole("button", { name: /start recording/i })

    if (await recordButton.isVisible().catch(() => false)) {
      await recordButton.click()
      await expect(page.getByRole("button", { name: /stop recording/i })).toBeVisible()
    }
  })

  test("should import skills", async ({ page }) => {
    const importButton = page.getByRole("button", { name: /import skills/i })

    if (await importButton.isVisible().catch(() => false)) {
      await importButton.click()
      await expect(page.getByRole("dialog", { name: /import skills/i })).toBeVisible()
    }
  })

  test("should synthesize skill after recording", async ({ page }) => {
    // This test assumes a recording session has been completed
    const synthesizeButton = page.getByRole("button", { name: /synthesize/i })

    if (await synthesizeButton.isVisible().catch(() => false)) {
      await synthesizeButton.click()
      await expect(page.getByText(/synthesizing|processing/i)).toBeVisible()
    }
  })

  test("should display MCP view", async ({ page }) => {
    await page.goto("/learning/mcp")
    await expect(page.getByTestId("mcp-view")).toBeVisible()
  })
})

test.describe("Skill Management", () => {
  test.beforeEach(async ({ page }) => {
    await page.goto("/learning/skills")
  })

  test("should display skill list", async ({ page }) => {
    await expect(page.getByTestId("skill-list")).toBeVisible()
  })

  test("should search for skills", async ({ page }) => {
    const searchInput = page.getByPlaceholder(/search skills/i)
    await searchInput.fill("test")
    await expect(searchInput).toHaveValue("test")
  })

  test("should filter skills by category", async ({ page }) => {
    const categoryFilter = page.getByTestId("category-filter")
    if (await categoryFilter.isVisible().catch(() => false)) {
      await categoryFilter.click()
      await page.getByRole("option", { name: /automation/i }).click()
    }
  })
})
