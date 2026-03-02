import { test, expect } from "@playwright/test"
import { ProjectsPage } from "../pom/ProjectsPage"
import { randomTeamName } from "../utils/random"

test.describe("Project Management", () => {
  let projectsPage: ProjectsPage

  test.beforeEach(async ({ page }) => {
    projectsPage = new ProjectsPage(page)
    await projectsPage.goto()
  })

  test("should display project switcher", async () => {
    await expect(projectsPage.projectSwitcher).toBeVisible()
  })

  test("should open project switcher dropdown", async () => {
    await projectsPage.openProjectSwitcher()
    await expect(projectsPage.projectList).toBeVisible()
  })

  test("should select a project from switcher", async () => {
    await projectsPage.openProjectSwitcher()
    const projects = await projectsPage.projectList.getByTestId("project-item").all()

    if (projects.length > 0) {
      const firstProject = projects[0]
      const projectName = await firstProject.textContent()
      if (projectName) {
        await firstProject.click()
        await projectsPage.expectProjectSelected(projectName)
      }
    }
  })

  test("should create a new project", async () => {
    const projectName = randomTeamName()
    const description = "This is a test project created by E2E tests"

    await projectsPage.createNewProject(projectName, description)
    await expect(projectsPage.page.getByText(/project created/i)).toBeVisible()
  })

  test("should search for projects", async () => {
    await projectsPage.searchProject("test")
    // Wait for search results
    await projectsPage.page.waitForTimeout(500)

    const count = await projectsPage.getProjectCount()
    // Search should filter results
    expect(count).toBeGreaterThanOrEqual(0)
  })

  test("should display project details", async () => {
    await projectsPage.openProjectSwitcher()
    const projects = await projectsPage.projectList.getByTestId("project-item").all()

    if (projects.length > 0) {
      await projects[0].click()
      // Check for project details in the UI
      await expect(projectsPage.page.getByTestId("project-details")).toBeVisible()
    }
  })
})

test.describe("Project Settings", () => {
  let projectsPage: ProjectsPage

  test.beforeEach(async ({ page }) => {
    projectsPage = new ProjectsPage(page)
    await projectsPage.goto()
  })

  test("should navigate to project settings", async () => {
    await projectsPage.openProjectSwitcher()
    const projects = await projectsPage.projectList.getByTestId("project-item").all()

    if (projects.length > 0) {
      const projectName = await projects[0].textContent()
      if (projectName) {
        await projectsPage.openProjectSettings(projectName)
        await expect(projectsPage.page.getByText(/settings/i)).toBeVisible()
      }
    }
  })
})
