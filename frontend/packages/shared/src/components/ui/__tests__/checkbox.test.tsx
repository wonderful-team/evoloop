import { describe, it, expect, vi } from "vitest"
import { render, screen, fireEvent } from "@testing-library/react"
import { Checkbox } from "../checkbox"

describe("Checkbox", () => {
  it("should render checkbox", () => {
    render(<Checkbox />)
    expect(screen.getByRole("checkbox")).toBeInTheDocument()
  })

  it("should handle checked state", () => {
    render(<Checkbox />)
    const checkbox = screen.getByRole("checkbox")

    fireEvent.click(checkbox)
    expect(checkbox).toHaveAttribute("data-state", "checked")

    fireEvent.click(checkbox)
    expect(checkbox).toHaveAttribute("data-state", "unchecked")
  })

  it("should call onCheckedChange when clicked", () => {
    const handleChange = vi.fn()
    render(<Checkbox onCheckedChange={handleChange} />)

    fireEvent.click(screen.getByRole("checkbox"))
    expect(handleChange).toHaveBeenCalledWith(true)
  })

  it("should be disabled when disabled prop is set", () => {
    render(<Checkbox disabled />)
    expect(screen.getByRole("checkbox")).toBeDisabled()
  })

  it("should apply custom className", () => {
    render(<Checkbox className="custom-checkbox" />)
    expect(screen.getByRole("checkbox")).toHaveClass("custom-checkbox")
  })

  it("should support defaultChecked", () => {
    render(<Checkbox defaultChecked />)
    expect(screen.getByRole("checkbox")).toHaveAttribute("data-state", "checked")
  })

  it("should support controlled checked state", () => {
    const { rerender } = render(<Checkbox checked={false} />)
    expect(screen.getByRole("checkbox")).toHaveAttribute("data-state", "unchecked")

    rerender(<Checkbox checked={true} />)
    expect(screen.getByRole("checkbox")).toHaveAttribute("data-state", "checked")
  })
})
