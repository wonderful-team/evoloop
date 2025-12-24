import { useQuery } from "@tanstack/react-query"
import { EvoLoopApi } from "@/client/evoloopClient"
import { Card, CardHeader, CardTitle, CardDescription } from "@/components/ui/card"
import { FolderOpen, Loader2 } from "lucide-react"

export function ProjectsScreen() {
    const { data, isLoading } = useQuery({
        queryKey: ['evoloop', 'projects'],
        queryFn: () => EvoLoopApi.getCloudProjects({ page: 1, page_size: 100 }),
    })

    const projects = data?.list || []

    return (
        <div className="p-4 bg-background min-h-full">
            <h1 className="text-xl font-bold mb-4">Projects</h1>

            {isLoading ? (
                <div className="flex justify-center p-8">
                    <Loader2 className="w-6 h-6 animate-spin text-muted-foreground" />
                </div>
            ) : (
                <div className="grid gap-3">
                    {projects.map((project: any) => (
                        <Card key={project.project_id}>
                            <CardHeader className="p-4">
                                <div className="flex items-center gap-3">
                                    <div className="w-10 h-10 bg-primary/10 rounded-lg flex items-center justify-center text-primary">
                                        <FolderOpen className="w-5 h-5" />
                                    </div>
                                    <div>
                                        <CardTitle className="text-base">{project.project_name}</CardTitle>
                                        <CardDescription className="text-xs mt-1">
                                            ID: {project.project_id}
                                        </CardDescription>
                                    </div>
                                </div>
                            </CardHeader>
                        </Card>
                    ))}
                    {projects.length === 0 && (
                        <div className="text-center text-muted-foreground text-sm py-8">
                            No projects found.
                        </div>
                    )}
                </div>
            )}
        </div>
    )
}
