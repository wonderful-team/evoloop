import { describe, it, expect, vi } from "vitest"
import { render, screen, fireEvent } from "@testing-library/react"
import { Button } from "../button"

describe("Button", () => {
  it("should render button with text", () => {
    render(<Button>Click me</Button>)
    expect(screen.getByRole("button", { name: /click me/i })).toBeInTheDocument()
  })

  it("should render with default variant", () => {
    const { container } = render(<Button>Default</Button>)
    expect(container.firstChild).toHaveAttribute("data-slot", "button")
  })

  it("should render different variants", () => {
    const variants = ["default", "destructive", "outline", "secondary", "ghost", "link"] as const

    variants.forEach((variant) => {
      const { container } = render(<Button variant={variant}>{variant}</Button>)
      expect(container.firstChild).toBeInTheDocument()
    })
  })

  it("should render different sizes", () => {
    const sizes = ["default", "sm", "lg", "icon", "icon-sm", "icon-lg"] as const

    sizes.forEach((size) => {
      const { container } = render(<Button size={size}>{size}</Button>)
      expect(container.firstChild).toBeInTheDocument()
    })
  })

  it("should handle click events", () => {
    const handleClick = vi.fn()
    render(<Button onClick={handleClick}>Click me</Button>)

    fireEvent.click(screen.getByRole("button"))
    expect(handleClick).toHaveBeenCalledTimes(1)
  })

  it("should be disabled when disabled prop is set", () => {
    render(<Button disabled>Disabled</Button>)
    expect(screen.getByRole("button")).toBeDisabled()
  })

  it("should not call onClick when disabled", () => {
    const handleClick = vi.fn()
    render(<Button disabled onClick={handleClick}>Disabled</Button>)

    fireEvent.click(screen.getByRole("button"))
    expect(handleClick).not.toHaveBeenCalled()
  })

  it("should support asChild prop", () => {
    render(
      <Button asChild>
        <a href="/test">Link Button</a>
      </Button>
    )
    expect(screen.getByRole("link", { name: /link button/i })).toBeInTheDocument()
  })

  it("should apply custom className", () => {
    const { container } = render(<Button className="custom-class">Custom</Button>)
    expect(container.firstChild).toHaveClass("custom-class")
  })

  it("should support type attribute", () => {
    render(<Button type="submit">Submit</Button>)
    expect(screen.getByRole("button")).toHaveAttribute("type", "submit")
  })

  it("should have focus styles", () => {
    render(<Button>Focusable</Button>)
    const button = screen.getByRole("button")
    button.focus()
    expect(button).toHaveFocus()
  })
})
