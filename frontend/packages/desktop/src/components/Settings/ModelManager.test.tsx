import { render, screen, fireEvent } from "@testing-library/react"
import { describe, it, expect, vi } from "vitest"
import { ModelManager, ModelItem } from "./ModelManager"
import * as useModelManagerModule from "@/hooks/useModelManager"

describe("ModelManager", () => {
  it("renders loading state", () => {
    vi.spyOn(useModelManagerModule, "useModelManager").mockReturnValue({
      models: [],
      loading: true,
      startDownload: vi.fn(),
    } as any)

    render(<ModelManager />)
    expect(screen.getByText("common.loading")).toBeInTheDocument()
  })

  it("renders model item with download button and triggers onDownload", () => {
    const onDownload = vi.fn()
    const model = {
      id: "whisper-tiny",
      name: "Whisper Tiny",
      size: "75MB",
      downloaded: false,
      status: "idle" as const,
      progress: null,
    }

    render(<ModelItem model={model as any} onDownload={onDownload} />)

    expect(screen.getByText("Whisper Tiny")).toBeInTheDocument()
    expect(screen.getByText("75MB")).toBeInTheDocument()
    expect(screen.getByText("settings.voice.modelNotDownloaded")).toBeInTheDocument()

    const downloadBtn = screen.getByText("settings.voice.modelDownloadBtn")
    fireEvent.click(downloadBtn)
    expect(onDownload).toHaveBeenCalled()
  })

  it("renders downloading progress bar when downloading", () => {
    const model = {
      id: "whisper-tiny",
      name: "Whisper Tiny",
      size: "75MB",
      downloaded: false,
      status: "downloading" as const,
      progress: 0.65,
    }

    render(<ModelItem model={model as any} onDownload={vi.fn()} />)

    expect(screen.getByText("settings.voice.modelDownloading")).toBeInTheDocument()
    expect(screen.getByText("65%")).toBeInTheDocument()
  })
})
