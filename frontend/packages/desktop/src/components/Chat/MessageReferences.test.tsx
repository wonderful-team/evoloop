import {render, screen} from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import {describe, expect, it, vi} from "vitest"
import {MessageReferences} from "./MessageReferences"

vi.mock("@/utils/fileLinkHandler", () => ({
  openExternalLink: vi.fn(),
  previewFile: vi.fn(),
  downloadFile: vi.fn(),
}))

// 重型子组件 mock（其模块顶层初始化在 jsdom 下不可用，且非测试面）
vi.mock("./Artifacts/EChartsArtifact", () => ({
  EChartsArtifact: () => <div data-testid="echarts" />,
}))
vi.mock("./Artifacts/HtmlArtifact", () => ({
  HtmlArtifact: () => <div data-testid="html-artifact" />,
}))
vi.mock("./Artifacts/MapArtifact", () => ({
  MapArtifact: () => <div data-testid="map-artifact" />,
}))
vi.mock("./Artifacts/ReactArtifact", () => ({
  ReactArtifact: () => <div data-testid="react-artifact" />,
}))
vi.mock("./Artifacts/TestReportCard", () => ({
  TestReportCard: () => <div data-testid="test-report" />,
}))

const imgRef = {
  id: "r1",
  type: "image" as const,
  target_id: "https://x.com/gen.png",
  target_name: "generated image",
}
const videoRef = {
  id: "r2",
  type: "video" as const,
  target_id: "https://x.com/clip.mp4",
  target_name: "generated video",
}
const fileRef = {
  id: "r3",
  type: "file" as const,
  target_id: "/tmp/report.pdf",
  target_name: "report.pdf",
}

describe("MessageReferences media grid", () => {
  it("renders an image reference as a thumbnail img", () => {
    render(<MessageReferences references={[imgRef]} />)
    const img = screen.getByRole("img")
    expect(img).toHaveAttribute("src", "https://x.com/gen.png")
  })

  it("renders a video reference as an inline player", () => {
    render(<MessageReferences references={[videoRef]} />)
    const video = document.querySelector("video")
    expect(video).toHaveAttribute("src", "https://x.com/clip.mp4")
  })

  it("renders AI-message images larger (w-80) than human uploads (w-24)", () => {
    const { container, unmount } = render(
      <MessageReferences references={[imgRef]} />,
    )
    expect(container.querySelector("button")?.className).toContain("w-80")
    unmount()

    const { container: c2 } = render(
      <MessageReferences references={[imgRef]} isUser={true} />,
    )
    expect(c2.querySelector("button")?.className).toContain("w-24")
    expect(c2.querySelector("button")?.className).not.toContain("w-80")
  })

  it("renders a file reference as a chip (not a thumbnail)", () => {
    render(<MessageReferences references={[fileRef]} />)
    expect(screen.getByText("report.pdf")).toBeInTheDocument()
    expect(document.querySelector("img")).toBeNull()
  })

  it("renders mixed media + chip refs together", () => {
    render(<MessageReferences references={[imgRef, videoRef, fileRef]} />)
    expect(screen.getByRole("img")).toBeInTheDocument()
    expect(document.querySelector("video")).toBeInTheDocument()
    expect(screen.getByText("report.pdf")).toBeInTheDocument()
  })

  it("returns null for empty references", () => {
    const { container } = render(<MessageReferences references={[]} />)
    expect(container).toBeEmptyDOMElement()
  })
})

describe("MessageReferences inline dedup", () => {
  it("hides image ref when content already inlines it as markdown image", () => {
    const content = "![generated image](https://x.com/gen.png)"
    render(<MessageReferences references={[imgRef]} content={content} />)
    expect(screen.queryByRole("img")).not.toBeInTheDocument()
  })

  it("hides video ref when content already inlines it as [Video:](url)", () => {
    const content = "[Video: generated video](https://x.com/clip.mp4)"
    render(<MessageReferences references={[videoRef]} content={content} />)
    expect(document.querySelector("video")).toBeNull()
  })

  it("keeps refs rendered when content mentions a different url", () => {
    const content = "![other](https://other.com/other.png)"
    render(<MessageReferences references={[imgRef]} content={content} />)
    expect(screen.getByRole("img")).toBeInTheDocument()
  })

  it("keeps refs rendered without content prop (legacy callers)", () => {
    render(<MessageReferences references={[imgRef]} />)
    expect(screen.getByRole("img")).toBeInTheDocument()
  })
})

describe("MessageReferences interaction", () => {
  it("fires onReferenceClick when a thumbnail is clicked", async () => {
    const onClick = vi.fn()
    render(<MessageReferences references={[imgRef]} onReferenceClick={onClick} />)
    await userEvent.click(screen.getByRole("img"))
    expect(onClick).toHaveBeenCalledWith(imgRef)
  })
})
