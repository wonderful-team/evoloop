import { render, screen, fireEvent } from "@testing-library/react"
import { describe, it, expect, vi } from "vitest"
import { CodeBlock } from "./CodeBlock"

vi.mock("@evoloop/shared/components/theme-provider", () => ({
  useTheme: () => ({ resolvedTheme: "dark" }),
}))

describe("CodeBlock", () => {
  it("renders code with language, line numbers, and copy button", () => {
    const code = 'const hello = "world";\nconsole.log(hello);'
    render(
      <CodeBlock
        language="typescript"
        codeString={code}
        isLong={false}
        lineCount={2}
      />,
    )

    expect(screen.getByText("typescript")).toBeInTheDocument()
    expect(screen.getByText("1")).toBeInTheDocument()
    expect(screen.getByText("2")).toBeInTheDocument()
    expect(screen.getByText("chat.messageList.copy")).toBeInTheDocument()

    const writeTextMock = vi.fn().mockResolvedValue(undefined)
    Object.assign(navigator, {
      clipboard: {
        writeText: writeTextMock,
      },
    })

    fireEvent.click(screen.getByText("chat.messageList.copy"))
    expect(writeTextMock).toHaveBeenCalledWith(code)
  })

  it("renders preview button when onPreview is provided", () => {
    const onPreview = vi.fn()
    const code = "<h1>Title</h1>"
    render(
      <CodeBlock
        language="html"
        codeString={code}
        isLong={true}
        lineCount={1}
        onPreview={onPreview}
      />,
    )

    expect(screen.getByText(/chat\.artifact\.lineCount/)).toBeInTheDocument()
    const previewBtn = screen.getByText("chat.messageList.preview")
    expect(previewBtn).toBeInTheDocument()

    fireEvent.click(previewBtn)
    expect(onPreview).toHaveBeenCalledWith(code)
  })
})
