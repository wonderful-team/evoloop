import { render, screen, fireEvent } from "@testing-library/react"
import { describe, it, expect, vi } from "vitest"
import { TTSButton } from "./TTSButton"
import * as useTTSModule from "@/hooks/useTTS"

vi.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (key: string) => {
      const dict: Record<string, string> = {
        "chat.tts.stop": "停止朗读",
        "chat.tts.speak": "朗读内容",
      }
      return dict[key] || key
    },
  }),
}))

describe("TTSButton", () => {
  it("renders idle volume icon and triggers speak on click", () => {
    const speakSpy = vi.fn()
    const stopSpy = vi.fn()
    vi.spyOn(useTTSModule, "useTTS").mockReturnValue({
      isSpeaking: false,
      isLoading: false,
      speak: speakSpy,
      stop: stopSpy,
      activeMessageId: null,
      voiceSpeed: 1,
      setVoiceSpeed: vi.fn(),
      volume: 1,
      setVolume: vi.fn(),
    } as any)

    render(<TTSButton text="Hello AI" />)

    const btn = screen.getByTitle("朗读内容")
    expect(btn).toBeInTheDocument()

    fireEvent.click(btn)
    expect(speakSpy).toHaveBeenCalledWith("Hello AI")
  })

  it("renders pause icon when speaking and triggers stop on click", () => {
    const speakSpy = vi.fn()
    const stopSpy = vi.fn()
    vi.spyOn(useTTSModule, "useTTS").mockReturnValue({
      isSpeaking: true,
      isLoading: false,
      speak: speakSpy,
      stop: stopSpy,
      activeMessageId: "msg-1",
      voiceSpeed: 1,
      setVoiceSpeed: vi.fn(),
      volume: 1,
      setVolume: vi.fn(),
    } as any)

    render(<TTSButton text="Hello AI" />)

    const btn = screen.getByTitle("停止朗读")
    expect(btn).toBeInTheDocument()

    fireEvent.click(btn)
    expect(stopSpy).toHaveBeenCalledTimes(1)
  })
})
