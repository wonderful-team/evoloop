import {render, screen} from "@testing-library/react"
import {describe, expect, it, vi} from "vitest"
import {MessageContent} from "./MessageContent"

// 重型子组件 mock（非测试面）
vi.mock("@/components/Common/Mermaid", () => ({
  Mermaid: () => <div data-testid="mermaid" />,
}))
vi.mock("./Artifacts/EChartsArtifact", () => ({
  EChartsArtifact: () => <div data-testid="echarts" />,
}))
vi.mock("./ChangesetSnapshotView", () => ({
  ChangesetSnapshot: () => <div data-testid="changeset" />,
}))
vi.mock("@/utils/fileLinkHandler", () => ({
  openExternalLink: vi.fn(),
  previewFile: vi.fn(),
  downloadFile: vi.fn(),
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

describe("MessageContent media tags", () => {
  it("renders [Image: name](url) as an img with the given url", () => {
    render(<MessageContent content="[Image: cat](https://x.com/cat.png)" />)
    const img = screen.getByRole("img")
    expect(img).toHaveAttribute("src", "https://x.com/cat.png")
  })

  it("renders legacy [Image: url] form (name doubles as url)", () => {
    render(<MessageContent content="[Image: https://x.com/legacy.png]" />)
    const img = screen.getByRole("img")
    expect(img).toHaveAttribute("src", "https://x.com/legacy.png")
  })

  it("renders [Video: name](url) as a video element", () => {
    render(<MessageContent content="[Video: clip](https://x.com/v.mp4)" />)
    const video = document.querySelector("video")
    expect(video).toHaveAttribute("src", "https://x.com/v.mp4")
  })

  it("renders [File: path] as a chip button with the filename", () => {
    render(<MessageContent content="[File: /tmp/report.pdf]" />)
    expect(screen.getByText("report.pdf")).toBeInTheDocument()
  })

  it("renders [Audio: name](url) as an audio element", () => {
    render(<MessageContent content="[Audio: voice](https://x.com/a.mp3)" />)
    const audio = document.querySelector("audio")
    expect(audio).toHaveAttribute("src", "https://x.com/a.mp3")
  })

  it("resolves uploads/ inline image tag through the raw-file endpoint", () => {
    render(<MessageContent content="[Image: uploads/pic.png]" />)
    const img = screen.getByRole("img")
    expect(img.getAttribute("src")).toBe(
      "/api/v1/files/raw?path=uploads%2Fpic.png",
    )
  })
})

describe("MessageContent markdown", () => {
  it("renders plain markdown text", () => {
    render(<MessageContent content="hello **world**" />)
    expect(screen.getByText(/hello/)).toBeInTheDocument()
  })

  it("renders markdown inline images", () => {
    render(<MessageContent content="![generated image](https://x.com/g.png)" />)
    const img = screen.getByRole("img")
    expect(img).toHaveAttribute("src", "https://x.com/g.png")
  })

  it("extracts <report> body as the displayed content", () => {
    render(<MessageContent content="<report>visible body</report>" />)
    expect(screen.getByText(/visible body/)).toBeInTheDocument()
  })

  it("hides <audit> tag content", () => {
    render(<MessageContent content={"<audit>secret thoughts</audit>\n\npublic text"} />)
    expect(screen.queryByText(/secret thoughts/)).not.toBeInTheDocument()
    expect(screen.getByText(/public text/)).toBeInTheDocument()
  })
})
