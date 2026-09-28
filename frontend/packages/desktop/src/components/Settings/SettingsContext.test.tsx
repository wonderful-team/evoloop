import { render, screen, fireEvent, waitFor } from "@testing-library/react"
import { describe, it, expect } from "vitest"
import { SettingsProvider, useSettings } from "./SettingsContext"
import { toast } from "sonner"

function TestConsumer() {
  const {
    isDirty,
    isSaving,
    setComponentDirty,
    registerSaveHandler,
    registerResetHandler,
    applyChanges,
    resetDraft,
  } = useSettings()

  return (
    <div>
      <span data-testid="dirty-status">{isDirty ? "dirty" : "clean"}</span>
      <span data-testid="saving-status">{isSaving ? "saving" : "idle"}</span>

      <button onClick={() => setComponentDirty("test-comp", true)}>Mark Dirty</button>
      <button onClick={() => setComponentDirty("test-comp", false)}>Mark Clean</button>
      <button
        onClick={() => {
          registerSaveHandler("test-comp", async () => {
            await new Promise((r) => setTimeout(r, 10))
          })
          registerResetHandler("test-comp", () => {})
        }}
      >
        Register Handlers
      </button>
      <button onClick={() => applyChanges()}>Apply Changes</button>
      <button onClick={() => resetDraft()}>Reset Draft</button>
    </div>
  )
}

describe("SettingsContext", () => {
  it("provides dirty tracking and reset handlers", () => {
    render(
      <SettingsProvider>
        <TestConsumer />
      </SettingsProvider>,
    )

    expect(screen.getByTestId("dirty-status")).toHaveTextContent("clean")

    // Mark dirty
    fireEvent.click(screen.getByText("Mark Dirty"))
    expect(screen.getByTestId("dirty-status")).toHaveTextContent("dirty")

    // Reset draft
    fireEvent.click(screen.getByText("Reset Draft"))
    expect(screen.getByTestId("dirty-status")).toHaveTextContent("clean")
    expect(toast.info).toHaveBeenCalledWith("settings.draftReset")
  })

  it("applies changes and triggers save handlers", async () => {
    render(
      <SettingsProvider>
        <TestConsumer />
      </SettingsProvider>,
    )

    fireEvent.click(screen.getByText("Register Handlers"))
    fireEvent.click(screen.getByText("Mark Dirty"))

    fireEvent.click(screen.getByText("Apply Changes"))

    await waitFor(() => {
      expect(toast.success).toHaveBeenCalledWith("settings.applySuccess", expect.anything())
      expect(screen.getByTestId("dirty-status")).toHaveTextContent("clean")
    })
  })
})
