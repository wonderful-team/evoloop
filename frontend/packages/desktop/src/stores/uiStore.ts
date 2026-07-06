import { create } from "zustand"

export interface PreviewDiffState {
  path: string
  diff: string
}

export interface PreviewFileState {
  path: string
  name: string
}

export interface UIState {
  // --- Overlays ---
  previewDiff: PreviewDiffState | null
  previewFile: PreviewFileState | null
  locateFilePath: string | null

  // Rewind Dialog
  isRewindDialogOpen: boolean
  rewindMode: "rewind" | "retry"
  rewindMessageId: string | undefined

  // --- Actions ---
  setPreviewDiff: (preview: PreviewDiffState | null) => void
  setPreviewFile: (preview: PreviewFileState | null) => void
  setLocateFilePath: (path: string | null) => void

  openRewindDialog: (
    messageId: string | undefined,
    mode: "rewind" | "retry",
  ) => void
  closeRewindDialog: () => void
}

export const useUIStore = create<UIState>((set) => ({
  // Initial State
  previewDiff: null,
  previewFile: null,
  locateFilePath: null,

  isRewindDialogOpen: false,
  rewindMode: "rewind",
  rewindMessageId: undefined,

  // Actions
  setPreviewDiff: (preview) => set({ previewDiff: preview }),
  setPreviewFile: (preview) => set({ previewFile: preview }),
  setLocateFilePath: (path) => set({ locateFilePath: path }),

  openRewindDialog: (messageId, mode) =>
    set({
      isRewindDialogOpen: true,
      rewindMessageId: messageId,
      rewindMode: mode,
    }),
  closeRewindDialog: () =>
    set({
      isRewindDialogOpen: false,
      rewindMessageId: undefined,
    }),
}))
