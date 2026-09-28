import { render, screen, fireEvent } from "@testing-library/react"
import { describe, it, expect, vi } from "vitest"
import { ImageGalleryViewer } from "./ImageGalleryViewer"

vi.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (key: string) => key,
  }),
}))

vi.mock("@/utils/fileUtils", () => ({
  resolveLocalFileSrc: (url: string) => url,
}))

describe("ImageGalleryViewer", () => {
  const images = [
    { url: "img1.png", name: "Screenshot 1" },
    { url: "img2.png", name: "Screenshot 2" },
    { url: "img3.png", name: "Screenshot 3" },
  ]

  it("renders current image and index indicator", () => {
    render(
      <ImageGalleryViewer
        images={images}
        index={0}
        open={true}
        onIndexChange={vi.fn()}
        onClose={vi.fn()}
      />,
    )

    expect(screen.getByText("1 / 3")).toBeInTheDocument()
    const mainImg = screen.getAllByRole("img")[0]
    expect(mainImg).toHaveAttribute("src", "img1.png")
  })

  it("navigates forward and backward via click and keyboard", () => {
    const onIndexChange = vi.fn()
    const onClose = vi.fn()

    render(
      <ImageGalleryViewer
        images={images}
        index={1}
        open={true}
        onIndexChange={onIndexChange}
        onClose={onClose}
      />,
    )

    // ArrowRight navigation
    fireEvent.keyDown(window, { key: "ArrowRight" })
    expect(onIndexChange).toHaveBeenCalledWith(2)

    // ArrowLeft navigation
    fireEvent.keyDown(window, { key: "ArrowLeft" })
    expect(onIndexChange).toHaveBeenCalledWith(0)
  })

  it("calls onClose when close button clicked", () => {
    const onClose = vi.fn()
    render(
      <ImageGalleryViewer
        images={images}
        index={0}
        open={true}
        onIndexChange={vi.fn()}
        onClose={onClose}
      />,
    )

    // Close button has X icon
    const closeBtn = screen.getAllByRole("button")[0]
    fireEvent.click(closeBtn)
    expect(onClose).toHaveBeenCalled()
  })
})
