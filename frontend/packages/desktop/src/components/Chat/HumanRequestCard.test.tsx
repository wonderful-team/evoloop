import { render, screen } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { describe, expect, it, vi } from "vitest"
import { HumanRequestCard as SharedHumanRequestCard } from "@evoloop/shared"
import type { HumanRequestItem } from "@evoloop/shared"

/**
 * 授权审批卡 grant_mode 四级治理动作（终态 v2）：
 * 授权门控请求（payload.resource_path 在场）显示「授权父目录」并回传 dir；
 * 普通审批不显示该按钮（避免对 macro:7 等非路径资源产生无意义父目录授权）。
 */
function baseRequest(overrides: Partial<HumanRequestItem> = {}): HumanRequestItem {
  return {
    id: "req-1",
    type: "approval",
    prompt: "读取 /Users/u/outside",
    status: "waiting_human",
    ...overrides,
  }
}

describe("SharedHumanRequestCard 授权父目录按钮", () => {
  it("授权门控请求显示「授权父目录」并回传 grantMode=dir", async () => {
    const onRespond = vi.fn().mockResolvedValue(undefined)
    render(
      <SharedHumanRequestCard
        request={baseRequest({
          payload: { resource_path: "/Users/u/outside", action: "read" },
        })}
        onRespond={onRespond}
      />,
    )

    // 测试环境 i18n 未初始化，t() 可能返回 key 或 defaultValue——宽松匹配文案或键名
    const btn = screen.getByText(/授权父目录|approveParentDir/)
    await userEvent.click(btn)
    expect(onRespond).toHaveBeenCalledWith(
      expect.stringMatching(/允许|approve/),
      "dir",
    )
  })

  it("普通审批不显示「授权父目录」", () => {
    render(<SharedHumanRequestCard request={baseRequest()} onRespond={vi.fn()} />)
    expect(screen.queryByText(/授权父目录|approveParentDir/)).toBeNull()
    expect(screen.getByText(/仅本次允许|approveOnce|Once/)).toBeTruthy()
  })

  it("拒绝按钮回传拒绝语义", async () => {
    const onRespond = vi.fn().mockResolvedValue(undefined)
    render(
      <SharedHumanRequestCard
        request={baseRequest({
          payload: { resource_path: "/p", action: "write" },
        })}
        onRespond={onRespond}
      />,
    )
    await userEvent.click(screen.getByText(/拒绝|reject/).closest("button")!)
    expect(onRespond).toHaveBeenCalledWith(
      expect.stringMatching(/拒绝|reject/),
      undefined,
    )
  })
})
