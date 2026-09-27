import { expect, type Page } from "@playwright/test"

export const isAuthed = () =>
  Boolean(process.env.E2E_USERNAME && process.env.E2E_PASSWORD)

/** CRITICAL: assert a page did not land on the global error boundary. */
export const expectNoCrash = async (page: Page) => {
  await expect(page.getByTestId("error-component")).toHaveCount(0)
}

/**
 * Mark setup as completed so the first-run SetupWizard dialog never appears
 * (mirrors `markSetupCompleted()` in the app). Callable as an init script so
 * it runs before any page code touches localStorage.
 */
export const setupDone = `
  if (!localStorage.getItem('evoloop_setup_completed')) {
    localStorage.setItem('evoloop_setup_completed', 'true')
  }
`
