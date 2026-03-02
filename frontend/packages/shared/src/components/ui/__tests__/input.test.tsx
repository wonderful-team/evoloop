import { describe, it, expect, vi } from "vitest"
import { render, screen, fireEvent } from "@testing-library/react"
import { Input } from "../input"

describe("Input", () => {
  it("should render input", () => {
    render(<Input />)
    expect(screen.getByRole("textbox")).toBeInTheDocument()
  })

  it("should render with placeholder", () => {
    render(<Input placeholder="Enter text" />)
    expect(screen.getByPlaceholderText("Enter text")).toBeInTheDocument()
  })

  it("should handle value changes", () => {
    render(<Input />)
    const input = screen.getByRole("textbox")

    fireEvent.change(input, { target: { value: "Hello" } })
    expect(input).toHaveValue("Hello")
  })

  it("should call onChange handler", () => {
    const handleChange = vi.fn()
    render(<Input onChange={handleChange} />)

    fireEvent.change(screen.getByRole("textbox"), { target: { value: "test" } })
    expect(handleChange).toHaveBeenCalled()
  })

  it("should support different types", () => {
    const { rerender } = render(<Input type="text" />)
    expect(screen.getByRole("textbox")).toHaveAttribute("type", "text")

    rerender(<Input type="password" />)
    expect(screen.getByRole("textbox")).toHaveAttribute("type", "password")

    rerender(<Input type="email" />)
    expect(screen.getByRole("textbox")).toHaveAttribute("type", "email")
  })

  it("should be disabled when disabled prop is set", () => {
    render(<Input disabled />)
    expect(screen.getByRole("textbox")).toBeDisabled()
  })

  it("should apply custom className", () => {
    render(<Input className="custom-input" />)
    expect(screen.getByRole("textbox")).toHaveClass("custom-input")
  })

  it("should support name attribute", () => {
    render(<Input name="username" />)
    expect(screen.getByRole("textbox")).toHaveAttribute("name", "username")
  })

  it("should support required attribute", () => {
    render(<Input required />)
    expect(screen.getByRole("textbox")).toBeRequired()
  })

  it("should support readOnly attribute", () => {
    render(<Input readOnly />)
    expect(screen.getByRole("textbox")).toHaveAttribute("readonly")
  })

  it("should have focus styles", () => {
    render(<Input />)
    const input = screen.getByRole("textbox")
    input.focus()
    expect(input).toHaveFocus()
  })

  it("should support defaultValue", () => {
    render(<Input defaultValue="Default text" />)
    expect(screen.getByRole("textbox")).toHaveValue("Default text")
  })

  it("should support aria attributes", () => {
    render(<Input aria-label="Search input" aria-describedby="search-help" />)
    const input = screen.getByRole("textbox")
    expect(input).toHaveAttribute("aria-label", "Search input")
    expect(input).toHaveAttribute("aria-describedby", "search-help")
  })
})
