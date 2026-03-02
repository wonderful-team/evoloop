import { describe, it, expect, vi } from "vitest"
import { render, screen, fireEvent, waitFor } from "@testing-library/react"
import {
  Dialog,
  DialogTrigger,
  DialogContent,
  DialogHeader,
  DialogFooter,
  DialogTitle,
  DialogDescription,
  DialogClose,
} from "../dialog"

// Mock useTranslation
vi.mock("react-i18next", () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}))

describe("Dialog", () => {
  it("should render dialog trigger", () => {
    render(
      <Dialog>
        <DialogTrigger>Open Dialog</DialogTrigger>
      </Dialog>
    )
    expect(screen.getByText("Open Dialog")).toBeInTheDocument()
  })

  it("should open dialog when trigger is clicked", async () => {
    render(
      <Dialog>
        <DialogTrigger>Open Dialog</DialogTrigger>
        <DialogContent>
          <DialogTitle>Dialog Title</DialogTitle>
        </DialogContent>
      </Dialog>
    )

    fireEvent.click(screen.getByText("Open Dialog"))

    await waitFor(() => {
      expect(screen.getByText("Dialog Title")).toBeInTheDocument()
    })
  })

  it("should render dialog with header, content, and footer", async () => {
    render(
      <Dialog defaultOpen>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Title</DialogTitle>
            <DialogDescription>Description</DialogDescription>
          </DialogHeader>
          <div>Main content</div>
          <DialogFooter>
            <button>Action</button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    )

    expect(screen.getByText("Title")).toBeInTheDocument()
    expect(screen.getByText("Description")).toBeInTheDocument()
    expect(screen.getByText("Main content")).toBeInTheDocument()
    expect(screen.getByText("Action")).toBeInTheDocument()
  })

  it("should close dialog when close button is clicked", async () => {
    render(
      <Dialog defaultOpen>
        <DialogContent>
          <DialogTitle>Title</DialogTitle>
        </DialogContent>
      </Dialog>
    )

    expect(screen.getByText("Title")).toBeInTheDocument()

    const closeButton = screen.getByRole("button", { name: /close/i })
    fireEvent.click(closeButton)

    await waitFor(() => {
      expect(screen.queryByText("Title")).not.toBeInTheDocument()
    })
  })

  it("should not show close button when showCloseButton is false", () => {
    render(
      <Dialog defaultOpen>
        <DialogContent showCloseButton={false}>
          <DialogTitle>Title</DialogTitle>
        </DialogContent>
      </Dialog>
    )

    const closeButtons = screen.queryAllByRole("button", { name: /close/i })
    expect(closeButtons).toHaveLength(0)
  })

  it("should apply custom className to dialog content", async () => {
    render(
      <Dialog defaultOpen>
        <DialogContent className="custom-dialog">
          <DialogTitle>Title</DialogTitle>
        </DialogContent>
      </Dialog>
    )

    const content = screen.getByText("Title").closest("[data-slot='dialog-content']")
    expect(content).toHaveClass("custom-dialog")
  })

  it("should render DialogClose as a button", () => {
    render(
      <Dialog defaultOpen>
        <DialogContent showCloseButton={false}>
          <DialogTitle>Title</DialogTitle>
          <DialogClose asChild>
            <button>Custom Close</button>
          </DialogClose>
        </DialogContent>
      </Dialog>
    )

    expect(screen.getByText("Custom Close")).toBeInTheDocument()
  })
})
