import { type Page, type Locator, expect } from "@playwright/test"

export class SettingsPage {
  readonly page: Page
  readonly profileTab: Locator
  readonly passwordTab: Locator
  readonly dangerZoneTab: Locator
  readonly saveButton: Locator
  readonly themeButton: Locator

  constructor(page: Page) {
    this.page = page
    this.profileTab = page.getByRole("tab", { name: /my profile/i })
    this.passwordTab = page.getByRole("tab", { name: /password/i })
    this.dangerZoneTab = page.getByRole("tab", { name: /danger zone/i })
    this.saveButton = page.getByRole("button", { name: /save/i })
    this.themeButton = page.getByTestId("theme-button")
  }

  async goto() {
    await this.page.goto("/settings")
    await this.waitForReady()
  }

  async waitForReady() {
    await expect(this.profileTab).toBeVisible()
  }

  async goToProfileTab() {
    await this.profileTab.click()
  }

  async goToPasswordTab() {
    await this.passwordTab.click()
  }

  async goToDangerZoneTab() {
    await this.dangerZoneTab.click()
  }

  async updateProfile(name: string, email: string) {
    await this.goToProfileTab()
    await this.page.getByRole("button", { name: /edit/i }).click()
    await this.page.getByLabel(/full name/i).fill(name)
    await this.page.getByLabel(/email/i).fill(email)
    await this.saveButton.click()
  }

  async changePassword(currentPassword: string, newPassword: string) {
    await this.goToPasswordTab()
    await this.page.getByTestId("current-password-input").fill(currentPassword)
    await this.page.getByTestId("new-password-input").fill(newPassword)
    await this.page.getByTestId("confirm-password-input").fill(newPassword)
    await this.page.getByRole("button", { name: /update password/i }).click()
  }

  async switchTheme(theme: "light" | "dark" | "system") {
    await this.themeButton.click()
    await this.page.getByTestId(`${theme}-mode`).click()
  }

  async expectTheme(theme: "light" | "dark") {
    await expect(this.page.locator("html")).toHaveClass(new RegExp(theme))
  }
}
