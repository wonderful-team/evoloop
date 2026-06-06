import { useChatStore } from "@/stores/chatStore"
import { useUIStore } from "@/stores/uiStore"
import { FilePreviewModal } from "@/components/Files/FilePreviewModal"
import { ProjectProfileDrawer } from "@/components/Files/ProjectProfileDrawer"
import { useProjectStore } from "@/stores/projectStore"

export function GlobalFilePreviewer() {
    const previewFile = useUIStore(s => s.previewFile)
    const setPreviewFile = useUIStore(s => s.setPreviewFile)
    const storeProjectId = useChatStore(s => s.projectId)
    const currentProject = useProjectStore(s => s.currentProject)
    
    const projectId = (currentProject?.id ?? storeProjectId) || 0

    return (
        <>
            <FilePreviewModal
                projectId={projectId}
                file={previewFile?.name !== "PROJECT.md" ? previewFile : null}
                open={!!previewFile && previewFile.name !== "PROJECT.md"}
                onOpenChange={(open) => !open && setPreviewFile(null)}
            />
            
            <ProjectProfileDrawer
                projectId={projectId}
                open={!!previewFile && previewFile.name === "PROJECT.md"}
                onOpenChange={(open) => !open && setPreviewFile(null)}
            />
        </>
    )
}
