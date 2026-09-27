import { renderHook } from "@testing-library/react"
import { toast } from "sonner"
import { describe, expect, it } from "vitest"
import useCustomToast from "./useCustomToast"

describe("useCustomToast hook", () => {
  it("calls sonner toast.success with translated title and description", () => {
    const { result } = renderHook(() => useCustomToast())
    result.current.showSuccessToast("操作已成功完成")

    expect(toast.success).toHaveBeenCalledWith("toast.success", {
      description: "操作已成功完成",
    })
  })

  it("calls sonner toast.error with translated title and description", () => {
    const { result } = renderHook(() => useCustomToast())
    result.current.showErrorToast("网络连接失败")

    expect(toast.error).toHaveBeenCalledWith("toast.error", {
      description: "网络连接失败",
    })
  })
})
