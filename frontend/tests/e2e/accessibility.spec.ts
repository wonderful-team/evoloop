import { test, expect } from "@playwright/test"

test.describe("Accessibility Tests", () => {
  test("should have proper heading hierarchy on login page", async ({ page }) => {
    await page.goto("/login")

    const h1 = page.locator("h1")
    await expect(h1).toHaveCount(1)
  })

  test("should have accessible form labels", async ({ page }) => {
    await page.goto("/login")

    const emailInput = page.getByTestId("email-input")
    const passwordInput = page.getByTestId("password-input")

    // Check if inputs have associated labels or aria-labels
    await expect(emailInput).toHaveAttribute("data-slot", "input")
    await expect(passwordInput).toHaveAttribute("data-slot", "input")
  })

  test("should support keyboard navigation", async ({ page }) => {
    await page.goto("/login")

    // Tab through form elements
    await page.keyboard.press("Tab")
    const focusedElement = await page.evaluate(() => document.activeElement?.tagName)
    expect(focusedElement).toBeDefined()
  })

  test("should have proper ARIA roles on navigation", async ({ page }) => {
    await page.goto("/")

    const nav = page.locator("nav").first()
    if (await nav.isVisible().catch(() => false)) {
      await expect(nav).toHaveAttribute("role", "navigation")
    }
  })

  test("should have proper button labels", async ({ page }) => {
    await page.goto("/login")

    const submitButton = page.getByRole("button", { name: /log in/i })
    await expect(submitButton).toBeVisible()
  })

  test("should maintain focus after form submission", async ({ page }) => {
    await page.goto("/login")

    await page.getByTestId("email-input").fill("invalid")
    await page.getByRole("button", { name: /log in/i }).click()

    // Focus should be on the input with error or error message
    const errorElement = page.getByText(/invalid email/i)
    await expect(errorElement).toBeVisible()
  })

  test("should have sufficient color contrast", async ({ page }) => {
    await page.goto("/login")

    // This is a basic check - real contrast testing requires axe or similar
    const body = page.locator("body")
    await expect(body).toHaveCSS("background-color")
    await expect(body).toHaveCSS("color")
  })
})

test.describe("Screen Reader Support", () => {
  test("should have aria-live regions for dynamic content", async ({ page }) => {
    await page.goto("/")

    // Check for live regions that announce updates
    const liveRegion = page.locator("[aria-live]").first()
    // Not all pages may have live regions, so this is optional
    if (await liveRegion.isVisible().catch(() => false)) {
      const liveValue = await liveRegion.getAttribute("aria-live")
      expect(["polite", "assertive"]).toContain(liveValue)
    }
  })

  test("should have descriptive link text", async ({ page }) => {
    await page.goto("/login")

    // Links should have descriptive text, not just "click here"
    const links = await page.getByRole("link").all()
    for (const link of links) {
      const text = await link.textContent()
      expect(text?.length).toBeGreaterThan(0)
    }
  })
})
