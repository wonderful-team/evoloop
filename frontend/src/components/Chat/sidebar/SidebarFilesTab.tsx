import { FileTree } from "@/components/Files/FileTree"

interface SidebarFilesTabProps {
    projectId?: number
}

export function SidebarFilesTab({ projectId }: SidebarFilesTabProps) {
    return (
        <div className="flex-1 overflow-y-auto min-h-0">
            <div className="p-2">
                {projectId && <FileTree projectId={projectId} onSelectFile={(file) => console.log(file)} />}
            </div>
        </div>
    )
}
