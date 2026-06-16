import { GlobalDiffViewer } from "@/components/Chat/GlobalDiffViewer"
import { GlobalFilePreviewer } from "@/components/Chat/GlobalFilePreviewer"
import { useUIStore } from "@/stores/uiStore"

export function GlobalOverlayManager() {
  const _isRewindDialogOpen = useUIStore((s) => s.isRewindDialogOpen)
  const _rewindMode = useUIStore((s) => s.rewindMode)
  const _rewindMessageId = useUIStore((s) => s.rewindMessageId)
  const _closeRewindDialog = useUIStore((s) => s.closeRewindDialog)

  // TODO: Connect RewindConfirmDialog confirm actions if necessary.
  // Wait, the confirm action in ChatInterface.tsx calls rewindMutation.mutate.
  // If we move it here, we either need to pass a callback or move the mutation logic.
  // Let's leave RewindConfirmDialog in ChatInterface for now and only handle Diff and File preview here,
  // or keep it but handle the confirm logic in ChatInterface using a store callback?
  // Actually, since this is Phase 1, let's start with just Diff and File Previewer to keep it simple and safe.

  return (
    <>
      <GlobalDiffViewer />
      <GlobalFilePreviewer />
      {/* Add more global overlays here as they are refactored */}
    </>
  )
}
