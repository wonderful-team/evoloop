import { render, screen, fireEvent } from "@testing-library/react"
import { describe, it, expect, vi } from "vitest"
import { ChangesetSnapshot } from "./ChangesetSnapshotView"

vi.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (key: string, opts?: any) => {
      if (key === "chat.changeset.more") {
        return `更多 +${opts?.count}`
      }
      const dict: Record<string, string> = {
        "chat.sidebar.agentChanges": "变更文件",
      }
      return dict[key] || key
    },
  }),
}))

describe("ChangesetSnapshot", () => {
  it("renders null when files array is empty", () => {
    const { container } = render(<ChangesetSnapshot files={[]} totalCount={0} />)
    expect(container).toBeEmptyDOMElement()
  })

  it("renders files with operation styles and triggers onViewDetails on click", () => {
    const onViewDetails = vi.fn()
    const files = [
      { path: "src/main.ts", operation: "added" as const, diff: "+const x = 1" },
      { path: "src/utils.ts", operation: "modified" as const, diff: "@@ -1 +1 @@" },
      { path: "src/old.ts", operation: "deleted" as const, diff: "-deleted" },
    ]

    render(
      <ChangesetSnapshot
        files={files}
        totalCount={3}
        onViewDetails={onViewDetails}
      />,
    )

    expect(screen.getByText("变更文件")).toBeInTheDocument()
    expect(screen.getByText("3")).toBeInTheDocument()
    expect(screen.getByText("main.ts")).toBeInTheDocument()
    expect(screen.getByText("utils.ts")).toBeInTheDocument()
    expect(screen.getByText("old.ts")).toBeInTheDocument()

    // Click on a file chip
    fireEvent.click(screen.getByText("main.ts"))
    expect(onViewDetails).toHaveBeenCalledWith("src/main.ts", "+const x = 1")
  })

  it("renders view all pill when totalCount > files.length", () => {
    const onViewDetails = vi.fn()
    const files = [
      { path: "src/a.ts", operation: "modified" as const },
    ]

    render(
      <ChangesetSnapshot
        files={files}
        totalCount={5}
        onViewDetails={onViewDetails}
      />,
    )

    const moreBtn = screen.getByText("更多 +4")
    expect(moreBtn).toBeInTheDocument()

    fireEvent.click(moreBtn)
    expect(onViewDetails).toHaveBeenCalledWith("")
  })
})
