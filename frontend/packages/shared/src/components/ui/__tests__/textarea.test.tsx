import { describe, it, expect, vi } from "vitest"
import { render, screen, fireEvent } from "@testing-library/react"
import { Textarea } from "../textarea"

describe("Textarea", () => {
  it("should render textarea", () => {
    render(<Textarea />)
    expect(screen.getByRole("textbox")).toBeInTheDocument()
  })

  it("should handle value changes", () => {
    render(<Textarea />)
    const textarea = screen.getByRole("textbox")

    fireEvent.change(textarea, { target: { value: "Hello\nWorld" } })
    expect(textarea).toHaveValue("Hello\nWorld")
  })

  it("should call onChange handler", () => {
    const handleChange = vi.fn()
    render(<Textarea onChange={handleChange} />)

    fireEvent.change(screen.getByRole("textbox"), { target: { value: "test" } })
    expect(handleChange).toHaveBeenCalled()
  })

  it("should be disabled when disabled prop is set", () => {
    render(<Textarea disabled />)
    expect(screen.getByRole("textbox")).toBeDisabled()
  })

  it("should apply custom className", () => {
    render(<Textarea className="custom-textarea" />)
    expect(screen.getByRole("textbox")).toHaveClass("custom-textarea")
  })

  it("should support placeholder", () => {
    render(<Textarea placeholder="Enter text..." />)
    expect(screen.getByPlaceholderText("Enter text...")).toBeInTheDocument()
  })

  it("should support name attribute", () => {
    render(<Textarea name="description" />)
    expect(screen.getByRole("textbox")).toHaveAttribute("name", "description")
  })

  it("should support required attribute", () => {
    render(<Textarea required />)
    expect(screen.getByRole("textbox")).toBeRequired()
  })

  it("should support readOnly attribute", () => {
    render(<Textarea readOnly />)
    expect(screen.getByRole("textbox")).toHaveAttribute("readonly")
  })

  it("should support rows attribute", () => {
    render(<Textarea rows={5} />)
    expect(screen.getByRole("textbox")).toHaveAttribute("rows", "5")
  })

  it("should support defaultValue", () => {
    render(<Textarea defaultValue="Default text" />)
    expect(screen.getByRole("textbox")).toHaveValue("Default text")
  })

  it("should have focus styles", () => {
    render(<Textarea />)
    const textarea = screen.getByRole("textbox")
    textarea.focus()
    expect(textarea).toHaveFocus()
  })

  it("should support aria attributes", () => {
    render(<Textarea aria-label="Description" aria-describedby="help-text" />)
    const textarea = screen.getByRole("textbox")
    expect(textarea).toHaveAttribute("aria-label", "Description")
    expect(textarea).toHaveAttribute("aria-describedby", "help-text")
  })
})
