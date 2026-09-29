import { expect, test } from "@playwright/test"
import { expectNoCrash, isAuthed, setupDone } from "./helpers"

/** Project detail routes — all parametrized by a real projectId. */
const PROJECT_PATHS = [
  { name: "project", suffix: "" },
  { name: "project overview", suffix: "/overview" },
  { name: "project profile", suffix: "/profile" },
  { name: "project tasks", suffix: "/tasks" },
  { name: "project files", suffix: "/files" },
  { name: "project vault", suffix: "/vault" },
  { name: "project wiki", suffix: "/wiki" },
  { name: "project macros", suffix: "/macros" },
  { name: "project generation", suffix: "/generation" },
  { name: "project duty", suffix: "/duty" },
  { name: "project assets", suffix: "/assets" },
  { name: "project v2", suffix: "/v2" },
  { name: "project v2 tasks", suffix: "/v2/tasks" },
  { name: "project v2 vault", suffix: "/v2/vault" },
  { name: "project v2 wiki", suffix: "/v2/wiki" },
  { name: "project v2 profile", suffix: "/v2/profile" },
  { name: "project v2 generation", suffix: "/v2/generation" },
  { name: "project v2 assets", suffix: "/v2/assets" },
]

test.describe("projects pages", () => {
  test.beforeEach(async ({ page }) => {
    await page.addInitScript(setupDone)
  })

  test("projects list renders project cards", async ({ page }) => {
    test.skip(!isAuthed(), "E2E credentials not configured")
    await page.goto("/#/projects")
    await expect(page).toHaveURL(/#\/projects$/)
    await expectNoCrash(page)
    await expect(
      page
        .getByRole("heading", { level: 1 })
        .filter({ hasText: /projects|项目/i }),
    ).toBeVisible({ timeout: 15_000 })
    // Either project cards or a create/import CTA on an empty workspace.
    const cards = page.locator("div[class*='cursor-pointer']")
    const cta = page.getByText(/new project|add project|新建项目|导入/i).first()
    expect((await cards.count()) > 0 || (await cta.count()) > 0).toBe(true)
  })

  test("project detail + subroutes render", async ({ page }) => {
    test.skip(!isAuthed(), "E2E credentials not configured")

    // Resolve a real projectId via the projects API using the session token
    // stored in localStorage (projects list navigates in JS, not <a href>).
    let projectId: string | null = null

    await page.goto("/#/chat")
    const token = await page.evaluate(() =>
      typeof window !== "undefined"
        ? localStorage.getItem("access_token")
        : null,
    )
    if (token) {
      const res = await page.request.get(
        "http://localhost:5173/api/v1/projects/",
        { headers: { Authorization: `Bearer ${token}` } },
      )
      if (res.ok()) {
        const data = (await res.json()) as {
          data?: { list?: Array<{ project_id: number | string }> }
        }
        const first = data?.data?.list?.[0]
        if (first) projectId = String(first.project_id)
      }
    }

    if (!projectId) {
      test.skip(true, "no projects exist for the test account")
    }

    for (const { name, suffix } of PROJECT_PATHS) {
      await test.step(name, async () => {
        const path = suffix
          ? `/projects/${projectId}${suffix}`
          : `/projects/${projectId}`
        await page.goto(`/#${path}`)
        await page.waitForLoadState("domcontentloaded")
        await expectNoCrash(page)
      })
    }
  })
})
