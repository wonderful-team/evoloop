import { describe, it, expect } from "vitest"
import { render, screen } from "@testing-library/react"
import { Alert, AlertTitle, AlertDescription } from "../alert"
import { AlertCircle } from "lucide-react"

describe("Alert", () => {
  it("should render alert with content", () => {
    render(
      <Alert>
        <AlertTitle>Alert Title</AlertTitle>
        <AlertDescription>Alert description text</AlertDescription>
      </Alert>
    )

    expect(screen.getByRole("alert")).toBeInTheDocument()
    expect(screen.getByText("Alert Title")).toBeInTheDocument()
    expect(screen.getByText("Alert description text")).toBeInTheDocument()
  })

  it("should render with default variant", () => {
    const { container } = render(
      <Alert>
        <AlertTitle>Default</AlertTitle>
      </Alert>
    )
    expect(container.firstChild).toHaveAttribute("data-slot", "alert")
  })

  it("should render with destructive variant", () => {
    const { container } = render(
      <Alert variant="destructive">
        <AlertTitle>Error</AlertTitle>
      </Alert>
    )
    expect(container.firstChild).toBeInTheDocument()
  })

  it("should render with icon", () => {
    render(
      <Alert>
        <AlertCircle data-testid="alert-icon" />
        <AlertTitle>With Icon</AlertTitle>
      </Alert>
    )

    expect(screen.getByTestId("alert-icon")).toBeInTheDocument()
    expect(screen.getByText("With Icon")).toBeInTheDocument()
  })

  it("should apply custom className", () => {
    const { container } = render(
      <Alert className="custom-alert">
        <AlertTitle>Custom</AlertTitle>
      </Alert>
    )
    expect(container.firstChild).toHaveClass("custom-alert")
  })

  it("should render title with correct data attribute", () => {
    render(
      <Alert>
        <AlertTitle>Test Title</AlertTitle>
      </Alert>
    )
    expect(screen.getByText("Test Title")).toHaveAttribute("data-slot", "alert-title")
  })

  it("should render description with correct data attribute", () => {
    render(
      <Alert>
        <AlertDescription>Test Description</AlertDescription>
      </Alert>
    )
    expect(screen.getByText("Test Description")).toHaveAttribute("data-slot", "alert-description")
  })

  it("should render complex alert with all elements", () => {
    render(
      <Alert variant="destructive">
        <AlertCircle data-testid="error-icon" />
        <AlertTitle>Error Occurred</AlertTitle>
        <AlertDescription>
          Something went wrong. Please try again later.
        </AlertDescription>
      </Alert>
    )

    expect(screen.getByRole("alert")).toBeInTheDocument()
    expect(screen.getByTestId("error-icon")).toBeInTheDocument()
    expect(screen.getByText("Error Occurred")).toBeInTheDocument()
    expect(screen.getByText(/something went wrong/i)).toBeInTheDocument()
  })
})
