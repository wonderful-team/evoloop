import { render, screen, fireEvent } from "@testing-library/react"
import { describe, it, expect, vi } from "vitest"
import { SettingsActionBar } from "./SettingsActionBar"
import * as SettingsContextModule from "./SettingsContext"

describe("SettingsActionBar", () => {
  it("renders null if not dirty and not saving", () => {
    vi.spyOn(SettingsContextModule, "useSettings").mockReturnValue({
      isDirty: false,
      isSaving: false,
      applyChanges: vi.fn(),
      resetDraft: vi.fn(),
    } as any)

    const { container } = render(<SettingsActionBar />)
    expect(container).toBeEmptyDOMElement()
  })

  it("renders pending changes banner and handles reset and apply", () => {
    const applySpy = vi.fn()
    const resetSpy = vi.fn()
    vi.spyOn(SettingsContextModule, "useSettings").mockReturnValue({
      isDirty: true,
      isSaving: false,
      applyChanges: applySpy,
      resetDraft: resetSpy,
    } as any)

    render(<SettingsActionBar />)

    expect(screen.getByText("settings.pendingChanges")).toBeInTheDocument()
    expect(screen.getByText("settings.restoreBtn")).toBeInTheDocument()
    expect(screen.getByText("settings.applyChangesBtn")).toBeInTheDocument()

    // Click reset
    fireEvent.click(screen.getByText("settings.restoreBtn"))
    expect(resetSpy).toHaveBeenCalledTimes(1)

    // Click apply
    fireEvent.click(screen.getByText("settings.applyChangesBtn"))
    expect(applySpy).toHaveBeenCalledTimes(1)
  })
})
