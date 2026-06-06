import { useUIStore } from "@/stores/uiStore"
import { DiffDrawer } from "./DiffDrawer"

export function GlobalDiffViewer() {
    const previewDiff = useUIStore(s => s.previewDiff)
    const setPreviewDiff = useUIStore(s => s.setPreviewDiff)

    return (
        <DiffDrawer
            isOpen={!!previewDiff}
            onClose={() => setPreviewDiff(null)}
            path={previewDiff?.path || null}
            diff={previewDiff?.diff || null}
        />
    )
}
