import { useQuery } from "@tanstack/react-query"
import { EvoLoopApi } from "@/client/evoloopClient"
import { Card, CardHeader, CardTitle, CardDescription } from "@/components/ui/card"
import { FolderOpen, Loader2, ArrowRight } from "lucide-react"
import { useMobileStore } from "../stores/useMobileStore"
import { useNavigate } from "@tanstack/react-router"
import { toast } from "sonner"

export function ProjectsScreen() {
    const navigate = useNavigate()
    const { setCurrentProject, setProjectInitialized } = useMobileStore()

    const { data, isLoading } = useQuery({
        queryKey: ['evoloop', 'projects'],
        queryFn: () => EvoLoopApi.getCloudProjects({ page: 1, page_size: 100 }),
    })

    const projects = data?.list || []

    const handleProjectClick = async (project: any) => {
        // Switch project context
        setCurrentProject(project)
        setProjectInitialized(true)

        // Find a device for this project (or any online device)
        try {
            const devices = await EvoLoopApi.getDeviceList();
            const onlineDevice = devices.find(d => d.status === 1);

            if (onlineDevice) {
                navigate({ to: `/chat/${onlineDevice.device_id}` as any })
                toast.success(`Opened ${project.project_name}`)
            } else {
                navigate({ to: '/devices' as any })
                toast.info(`Switched to ${project.project_name}. Select a device.`)
            }
        } catch {
            navigate({ to: '/projects' as any })
        }
    }

    return (
        <div className="flex flex-col h-full bg-background">
            <div className="px-4 pt-6 pb-2 shrink-0">
                <h1 className="text-xl font-bold">Projects</h1>
            </div>

            <div className="flex-1 overflow-y-auto px-4 pb-4">
                {isLoading ? (
                    <div className="flex justify-center p-8">
                        <Loader2 className="w-6 h-6 animate-spin text-muted-foreground" />
                    </div>
                ) : (
                    <div className="grid gap-3 pb-20"> {/* Add padding for bottom tabs */}
                        {projects.map((project: any) => (
                            <Card
                                key={project.project_id}
                                className="active:scale-[0.99] transition-transform cursor-pointer hover:bg-muted/50"
                                onClick={() => handleProjectClick(project)}
                            >
                                <CardHeader className="p-4">
                                    <div className="flex items-center gap-3">
                                        <div className="w-10 h-10 bg-primary/10 rounded-lg flex items-center justify-center text-primary shrink-0">
                                            <FolderOpen className="w-5 h-5" />
                                        </div>
                                        <div className="flex-1 min-w-0">
                                            <CardTitle className="text-base truncate">{project.project_name}</CardTitle>
                                            <CardDescription className="text-xs mt-1">
                                                ID: {project.project_id}
                                            </CardDescription>
                                        </div>
                                        <ArrowRight className="w-4 h-4 text-muted-foreground/50" />
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
        </div>
    )
}
