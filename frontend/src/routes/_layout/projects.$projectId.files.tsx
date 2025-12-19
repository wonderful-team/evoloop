import { createFileRoute } from '@tanstack/react-router'
import { useProjectStore } from "@/stores/projectStore"
import { Folder, AlertCircle, FileCode, Loader2 } from "lucide-react"
import { useEffect, useState } from "react"
import { useQuery } from "@tanstack/react-query"
import { FilesService } from "@/client"
import { FileTree } from "@/components/Files/FileTree"

export const Route = createFileRoute('/_layout/projects/$projectId/files')({
    component: FilesPage,
})

function FilesPage() {
    const { projectId } = Route.useParams()
    const { currentProject, projects, fetchProjects, setProject } = useProjectStore()
    const [selectedFile, setSelectedFile] = useState<{ path: string, name: string } | null>(null)

    // Sync params with store on mount or update
    useEffect(() => {
        if (!projectId) return

        // If we have projects but current doesn't match, find and set
        if (projects.length > 0) {
            const p = projects.find(p => p.id === Number(projectId))
            if (p && p.id !== currentProject?.id) {
                setProject(p)
            }
        } else {
            // If no projects loaded (e.g. refresh), fetch them
            fetchProjects()
        }
    }, [projectId, projects, currentProject, fetchProjects, setProject])

    // Load file content
    const { data: fileContent, isLoading: isContentLoading } = useQuery({
        queryKey: ["fileContent", projectId, selectedFile?.path],
        queryFn: () => FilesService.getFileContent({ projectId: Number(projectId), path: selectedFile!.path }),
        enabled: !!selectedFile && !!projectId
    })

    // Loading state or lookup
    const displayProject = currentProject?.id === Number(projectId) ? currentProject : projects.find(p => p.id === Number(projectId))

    if (!displayProject) {
        return (
            <div className="flex flex-col items-center justify-center h-[calc(100vh-8rem)] text-muted-foreground">
                <AlertCircle className="h-12 w-12 mb-4 opacity-20" />
                <h3 className="text-lg font-medium">Project Not Found</h3>
                <p>Could not find project with ID: {projectId}</p>
            </div>
        )
    }

    return (
        <div className="flex flex-1 h-[calc(100vh-4rem)] overflow-hidden">
            {/* Sidebar with FileTree */}
            <div className="w-72 border-r bg-muted/5 flex flex-col">
                <div className="p-3 border-b flex items-center gap-2 bg-muted/10">
                    <Folder className="h-4 w-4 text-primary" />
                    <span className="font-semibold text-sm truncate" title={displayProject.name}>
                        {displayProject.name}
                    </span>
                </div>
                <div className="flex-1 overflow-auto py-2">
                    <FileTree
                        projectId={Number(projectId)}
                        onSelectFile={(node) => setSelectedFile({ path: node.path, name: node.name })}
                    />
                </div>
            </div>

            {/* Content Area */}
            <div className="flex-1 flex flex-col bg-background min-w-0">
                {selectedFile ? (
                    <>
                        <div className="h-10 border-b px-4 flex items-center gap-2 bg-muted/5 text-sm">
                            <FileCode className="h-4 w-4 text-muted-foreground" />
                            <span className="font-medium">{selectedFile.name}</span>
                            <span className="text-xs text-muted-foreground ml-auto opacity-50 font-mono truncate max-w-[300px]" title={selectedFile.path}>
                                {selectedFile.path}
                            </span>
                        </div>
                        <div className="flex-1 overflow-auto p-0">
                            {isContentLoading ? (
                                <div className="h-full flex items-center justify-center text-muted-foreground text-sm">
                                    <Loader2 className="h-4 w-4 animate-spin mr-2" />
                                    Loading content...
                                </div>
                            ) : (
                                <pre className="p-4 font-mono text-sm text-foreground/90 overflow-auto whitespace-pre-wrap break-all">
                                    {(fileContent as any)?.content || ""}
                                </pre>
                            )}
                        </div>
                    </>
                ) : (
                    <div className="flex-1 flex flex-col items-center justify-center text-muted-foreground/50 bg-muted/5">
                        <FileCode className="h-16 w-16 mb-4 opacity-10" />
                        <p>Select a file to view code</p>
                    </div>
                )}
            </div>
        </div>
    )
}
