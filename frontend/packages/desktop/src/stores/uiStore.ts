import {create} from "zustand"

export interface PreviewDiffState {
  path: string
  diff: string
}

export interface PreviewFileState {
  path: string
  name: string
}

function initialShowContextPanel(): boolean {
  if (typeof window === "undefined") return false
  const saved = localStorage.getItem("chat.contextPanel.hidden")
  if (saved === "true") return false
  if (window.innerWidth < 1024) return false
  return true
}

function initialIsCompactWindow(): boolean {
  if (typeof window === "undefined") return false
  return window.innerWidth < 1024
}

export interface UIState {
  // --- Overlays ---
  previewDiff: PreviewDiffState | null
  previewFile: PreviewFileState | null
  locateFilePath: string | null

  // --- Chat layout (lifted from ChatInterface so the titlebar slot can
  //     render chat-contextual actions without prop drilling) ---
  isCompactWindow: boolean
  showContextPanel: boolean
  showChatListSheet: boolean
  showChatList: boolean
  miniMode: boolean

  // --- Actions ---
  setPreviewDiff: (preview: PreviewDiffState | null) => void
  setPreviewFile: (preview: PreviewFileState | null) => void
  setLocateFilePath: (path: string | null) => void

  setIsCompactWindow: (v: boolean) => void
  setShowContextPanel: (v: boolean) => void
  setShowChatListSheet: (v: boolean) => void
  setShowChatList: (v: boolean) => void
  setMiniMode: (v: boolean) => void
}

export const useUIStore = create<UIState>((set) => ({
  // Initial State
  previewDiff: null,
  previewFile: null,
  locateFilePath: null,

  isCompactWindow: initialIsCompactWindow(),
  showContextPanel: initialShowContextPanel(),
  showChatListSheet: false,
  showChatList: true,
  miniMode: false,

  // Actions
  setPreviewDiff: (preview) => set({ previewDiff: preview }),
  setPreviewFile: (preview) => set({ previewFile: preview }),
  setLocateFilePath: (path) => set({ locateFilePath: path }),

  setIsCompactWindow: (v) => set({ isCompactWindow: v }),
  setShowContextPanel: (v) => set({ showContextPanel: v }),
  setShowChatListSheet: (v) => set({ showChatListSheet: v }),
  setShowChatList: (v) => set({ showChatList: v }),
  setMiniMode: (v) => set({ miniMode: v }),
}))

// Compact-window listener（一次性注册）：缩窗时关闭上下文面板，
// 否则它会以 Sheet 形式覆盖聊天区。
if (typeof window !== "undefined") {
  const mql = window.matchMedia("(max-width: 1023px)")
  mql.addEventListener("change", (e) => {
    useUIStore.getState().setIsCompactWindow(e.matches)
    if (e.matches) useUIStore.getState().setShowContextPanel(false)
  })
}
