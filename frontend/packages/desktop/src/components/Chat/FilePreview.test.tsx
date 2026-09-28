import { render, screen, fireEvent } from "@testing-library/react"
import { describe, it, expect, vi } from "vitest"
import { FilePreview, type PickedFile } from "./FilePreview"

vi.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (key: string) => {
      const dict: Record<string, string> = {
        "common.preview": "预览",
        "chat.interface.uploading": "上传中",
        "chat.interface.uploadFailed": "上传失败",
      }
      return dict[key] || key
    },
  }),
}))

describe("FilePreview", () => {
  it("renders null if pickedFiles is empty", () => {
    const { container } = render(<FilePreview pickedFiles={[]} onRemove={vi.fn()} />)
    expect(container).toBeEmptyDOMElement()
  })

  it("renders different file types and statuses and handles remove & click", () => {
    const onRemove = vi.fn()
    const onClick = vi.fn()
    const files: PickedFile[] = [
      { id: "1", name: "logo.png", url: "http://example.com/logo.png", type: "image", status: "success" },
      { id: "2", name: "recording.mp3", url: "audio.mp3", type: "audio", status: "uploading" },
      { id: "3", name: "bad.pdf", url: "bad.pdf", type: "file", status: "error" },
    ]

    render(<FilePreview pickedFiles={files} onRemove={onRemove} onClick={onClick} />)

    expect(screen.getByText("logo.png")).toBeInTheDocument()
    expect(screen.getByText("recording.mp3")).toBeInTheDocument()
    expect(screen.getByText("上传中")).toBeInTheDocument()
    expect(screen.getByText("bad.pdf")).toBeInTheDocument()
    expect(screen.getByText("上传失败")).toBeInTheDocument()

    // Click file item
    fireEvent.click(screen.getByText("logo.png"))
    expect(onClick).toHaveBeenCalledWith(files[0])

    // Click remove button (button with X icon)
    const removeButtons = screen.getAllByRole("button")
    fireEvent.click(removeButtons[0])
    expect(onRemove).toHaveBeenCalledWith("1")
  })
})
