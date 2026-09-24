import {GlobalDiffViewer} from "@/components/Chat/GlobalDiffViewer"
import {GlobalFilePreviewer} from "@/components/Chat/GlobalFilePreviewer"

export function GlobalOverlayManager() {
  // 审计清理：rewind 预留订阅删除（声明后从未使用，且订阅会让 uiStore
  // 的 rewind 字段变化触发本组件无谓重渲染）。RewindConfirmDialog 实际
  // 由 ChatInterface 本地 state 管理；若未来迁移到全局 overlay 再加回。

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
