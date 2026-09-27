import { render, screen } from "@testing-library/react"
import { describe, expect, it } from "vitest"
import { CostBlock, PulseWave } from "./AgentPulse"

describe("AgentPulse component suite", () => {
  it("renders CostBlock with formatted tokens and duty duration", () => {
    const now = 1700000000000
    const dashboard = {
      tokens: {
        today: { input: 1200, output: 800 },
        week: { input: 50000, output: 55000 },
      },
      today_window: {
        since: new Date(now - (3600 * 2 + 15 * 60) * 1000).toISOString(),
      },
    } as any

    render(<CostBlock dashboard={dashboard} now={now} />)

    expect(screen.getByText("今日消耗")).toBeInTheDocument()
    // 2000 -> 2.0K
    expect(screen.getByText("2.0K")).toBeInTheDocument()
    expect(screen.getByText("本周累计")).toBeInTheDocument()
    // 105000 -> 105.0K
    expect(screen.getByText("105.0K")).toBeInTheDocument()
    expect(screen.getByText("在岗时长")).toBeInTheDocument()
    expect(screen.getByText("2h 15m")).toBeInTheDocument()
  })

  it("handles missing dashboard metrics gracefully", () => {
    render(<CostBlock now={Date.now()} />)
    expect(screen.getByText("今日消耗")).toBeInTheDocument()
    expect(screen.getAllByText("0").length).toBeGreaterThan(0)
    expect(screen.getByText("—")).toBeInTheDocument()
  })

  it("renders PulseWave in inactive and active states", () => {
    const { container, rerender } = render(<PulseWave active={false} />)
    const waveInactive = container.querySelector("[data-active]")
    expect(waveInactive).toHaveAttribute("data-active", "false")

    rerender(<PulseWave active={true} />)
    const waveActive = container.querySelector("[data-active]")
    expect(waveActive).toHaveAttribute("data-active", "true")
  })
})
