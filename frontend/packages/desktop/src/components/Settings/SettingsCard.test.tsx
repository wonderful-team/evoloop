import { render, screen } from "@testing-library/react"
import { describe, it, expect } from "vitest"
import { SettingsCard } from "./SettingsCard"
import { Settings } from "lucide-react"

describe("SettingsCard", () => {
  it("renders card with icon, title, description, headerExtra and children", () => {
    render(
      <SettingsCard
        icon={Settings}
        title="通用偏好"
        description="系统基础设置项"
        headerExtra={<span data-testid="extra">额外操作</span>}
      >
        <div data-testid="child-content">设置内容</div>
      </SettingsCard>,
    )

    expect(screen.getByText("通用偏好")).toBeInTheDocument()
    expect(screen.getByText("系统基础设置项")).toBeInTheDocument()
    expect(screen.getByTestId("extra")).toBeInTheDocument()
    expect(screen.getByTestId("child-content")).toBeInTheDocument()
  })
})
