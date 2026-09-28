import { render, screen, fireEvent } from "@testing-library/react"
import { describe, it, expect, vi } from "vitest"
import { RewindConfirmDialog } from "./RewindConfirmDialog"

describe("RewindConfirmDialog", () => {
  it("renders rewind mode with title and file revert checkbox checked by default", () => {
    const onConfirm = vi.fn()
    const onOpenChange = vi.fn()

    render(
      <RewindConfirmDialog
        open={true}
        onOpenChange={onOpenChange}
        onConfirm={onConfirm}
        mode="rewind"
      />,
    )

    expect(screen.getByText("chat.rewind.confirmTitle")).toBeInTheDocument()
    expect(screen.getByText("chat.rewind.confirmDescription")).toBeInTheDocument()
    const checkbox = screen.getByRole("checkbox")
    expect(checkbox).toBeChecked()

    fireEvent.click(screen.getByText("chat.rewind.confirm"))
    expect(onConfirm).toHaveBeenCalledWith(true)
  })

  it("toggling revertFiles passes false onConfirm", () => {
    const onConfirm = vi.fn()
    const onOpenChange = vi.fn()

    render(
      <RewindConfirmDialog
        open={true}
        onOpenChange={onOpenChange}
        onConfirm={onConfirm}
        mode="rewind"
      />,
    )

    const checkbox = screen.getByRole("checkbox")
    fireEvent.click(checkbox)

    fireEvent.click(screen.getByText("chat.rewind.confirm"))
    expect(onConfirm).toHaveBeenCalledWith(false)
  })

  it("renders retry mode titles and buttons correctly", () => {
    const onConfirm = vi.fn()
    const onOpenChange = vi.fn()

    render(
      <RewindConfirmDialog
        open={true}
        onOpenChange={onOpenChange}
        onConfirm={onConfirm}
        mode="retry"
      />,
    )

    expect(screen.getByText("chat.retry.confirmTitle")).toBeInTheDocument()
    expect(screen.getByText("chat.retry.confirmDescription")).toBeInTheDocument()
    expect(screen.getByText("chat.retry.confirm")).toBeInTheDocument()
  })
})
