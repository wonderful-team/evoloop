import { type Page, type Locator, expect } from "@playwright/test"

export class ProjectsPage {
  readonly page: Page
  readonly projectSwitcher: Locator
  readonly newProjectButton: Locator
  readonly projectList: Locator
  readonly projectSearch: Locator

  constructor(page: Page) {
    this.page = page
    this.projectSwitcher = page.getByTestId("project-switcher")
    this.newProjectButton = page.getByRole("button", { name: /new project/i })
    this.projectList = page.getByTestId("project-list")
    this.projectSearch = page.getByPlaceholder(/search projects/i)
  }

  async goto() {
    await this.page.goto("/projects")
    await this.waitForReady()
  }

  async waitForReady() {
    await expect(this.projectSwitcher).toBeVisible()
  }

  async openProjectSwitcher() {
    await this.projectSwitcher.click()
  }

  async selectProject(projectName: string) {
    await this.openProjectSwitcher()
    await this.page.getByRole("menuitem", { name: projectName }).click()
  }

  async createNewProject(name: string, description?: string) {
    await this.newProjectButton.click()
    await this.page.getByLabel(/project name/i).fill(name)
    if (description) {
      await this.page.getByLabel(/description/i).fill(description)
    }
    await this.page.getByRole("button", { name: /create/i }).click()
  }

  async expectProjectSelected(projectName: string) {
    await expect(this.projectSwitcher).toContainText(projectName)
  }

  async searchProject(query: string) {
    await this.projectSearch.fill(query)
  }

  async getProjectCount() {
    return this.projectList.getByTestId("project-item").count()
  }

  async openProjectSettings(projectName: string) {
    await this.page.getByTestId(`project-${projectName}`).getByRole("button", { name: /settings/i }).click()
  }
}
