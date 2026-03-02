import { describe, it, expect, vi } from "vitest"
import { extractErrorMessage, handleError, getInitials } from "../utils"
import { AxiosError } from "axios"

describe("extractErrorMessage", () => {
  it("should extract message from AxiosError", () => {
    const axiosError = new AxiosError("Network Error")
    const result = extractErrorMessage(axiosError as any)
    expect(result).toBe("Network Error")
  })

  it("should extract message from API error with array detail", () => {
    const apiError = {
      body: {
        detail: [{ msg: "Field is required" }],
      },
    }
    const result = extractErrorMessage(apiError as any)
    expect(result).toBe("Field is required")
  })

  it("should extract message from API error with string detail", () => {
    const apiError = {
      body: {
        detail: "Something went wrong",
      },
    }
    const result = extractErrorMessage(apiError as any)
    expect(result).toBe("Something went wrong")
  })

  it("should return default message when no detail", () => {
    const apiError = {
      body: {},
    }
    const result = extractErrorMessage(apiError as any)
    expect(result).toBe("Something went wrong.")
  })

  it("should return default message for empty error", () => {
    const result = extractErrorMessage({} as any)
    expect(result).toBe("Something went wrong.")
  })
})

describe("handleError", () => {
  it("should call error handler with message", () => {
    const showErrorToast = vi.fn()
    const apiError = {
      body: {
        detail: "Test error message",
      },
    }

    handleError.call(showErrorToast, apiError as any)

    expect(showErrorToast).toHaveBeenCalledWith("Test error message")
  })

  it("should bind correctly when used with .bind", () => {
    const showErrorToast = vi.fn()
    const boundHandleError = handleError.bind(showErrorToast)
    const apiError = {
      body: {
        detail: "Bound error",
      },
    }

    boundHandleError(apiError as any)

    expect(showErrorToast).toHaveBeenCalledWith("Bound error")
  })
})

describe("getInitials", () => {
  it("should return initials from single name", () => {
    const result = getInitials("John")
    expect(result).toBe("J")
  })

  it("should return initials from first and last name", () => {
    const result = getInitials("John Doe")
    expect(result).toBe("JD")
  })

  it("should return initials from multiple names (only first two)", () => {
    const result = getInitials("John Michael Doe")
    expect(result).toBe("JM")
  })

  it("should return uppercase initials", () => {
    const result = getInitials("john doe")
    expect(result).toBe("JD")
  })

  it("should handle empty string", () => {
    const result = getInitials("")
    expect(result).toBe("")
  })

  it("should handle names with extra spaces", () => {
    const result = getInitials("John  Doe")
    expect(result).toBe("JD")
  })

  it("should handle single letter names", () => {
    const result = getInitials("A B C")
    expect(result).toBe("AB")
  })
})
