import { render, screen, waitFor } from "@testing-library/react"
import { describe, it, expect, vi } from "vitest"
import { DiffDrawer } from "./DiffDrawer"
import * as Diff2Html from "diff2html"

vi.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (key: string) => {
      const dict: Record<string, string> = {
        "chat.diff.tip": "提示：绿色表示新增，红色表示删除",
        "common.loading": "正在生成 Diff...",
      }
      return dict[key] || key
    },
  }),
}))

vi.mock("@/components/Common/AppSheet", () => ({
  AppSheet: ({ children, title, subtitle, footer }: any) => (
    <div data-testid="app-sheet">
      <div data-testid="sheet-title">{title}</div>
      <div data-testid="sheet-subtitle">{subtitle}</div>
      <div data-testid="sheet-body">{children}</div>
      <div data-testid="sheet-footer">{footer}</div>
    </div>
  ),
}))

vi.mock("diff2html", () => ({
  html: vi.fn().mockReturnValue('<div class="diff-content">+ new line</div>'),
  ColorSchemeType: { DARK: "dark" },
}))

describe("DiffDrawer", () => {
  it("renders null if path or diff is missing or closed", () => {
    const { container: c1 } = render(
      <DiffDrawer isOpen={true} onClose={vi.fn()} path={null} diff="some diff" />,
    )
    expect(c1).toBeEmptyDOMElement()

    const { container: c2 } = render(
      <DiffDrawer isOpen={true} onClose={vi.fn()} path="src/index.ts" diff={null} />,
    )
    expect(c2).toBeEmptyDOMElement()
  })

  it("renders sheet and transforms diff via Diff2Html when open", async () => {
    render(
      <DiffDrawer
        isOpen={true}
        onClose={vi.fn()}
        path="src/components/Button.tsx"
        diff="--- a\n+++ b"
      />,
    )

    expect(screen.getByTestId("sheet-title")).toHaveTextContent("Button.tsx")
    expect(screen.getByTestId("sheet-subtitle")).toHaveTextContent("src/components/Button.tsx")
    expect(screen.getByTestId("sheet-footer")).toHaveTextContent("提示：绿色表示新增，红色表示删除")

    await waitFor(() => {
      expect(Diff2Html.html).toHaveBeenCalled()
      expect(document.querySelector(".diff-content")).not.toBeNull()
    })
  })
})
