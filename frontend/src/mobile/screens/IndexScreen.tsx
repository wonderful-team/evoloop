import { ArrowRight, Clock, Search } from "lucide-react"
import { Logo } from "@/components/Common/Logo"
import { Card, CardContent } from "@/components/ui/card"
import { Button } from "@/components/ui/button"
import { useNavigate } from "@tanstack/react-router"
import { useQuery } from "@tanstack/react-query"
import { EvoLoopApi } from "@/client/evoloopClient"
import { ChatInput } from "../components/chat/ChatInput"
import { useMobileStore } from "../stores/useMobileStore"
import { toast } from "sonner"

export function IndexScreen() {
    const navigate = useNavigate()
    const { setCurrentProject, setProjectInitialized } = useMobileStore()

    // Fetch Recent Projects
    const { data: projectsData, isLoading } = useQuery({
        queryKey: ['evoloop', 'projects', 'recent'],
        queryFn: () => EvoLoopApi.getCloudProjects({ page: 1, page_size: 10 }),
    })
    const recentProjects = projectsData?.list || []

    const handleInputSend = async (content: string) => {
        // Need to find a target device.
        // For now, let's navigate to device selection but PASS the content?
        // Or if we have a "default" device?
        // Let's look for ANY online device.
        try {
            const devices = await EvoLoopApi.getDeviceList();
            const onlineDevice = devices.find(d => d.status === 1);

            if (onlineDevice) {
                // Navigate to chat with that device, and we need a way to pass the initial message.
                // We can use search params or state.
                // But ChatScreen doesn't read initial message from search params yet.
                // Updating ChatScreen to read 'initialMessage'?
                // Or simplified: Just go to /devices and toast?
                // User requirement: "Click send... jump to ChatScreen".
                // So we MUST jump to a ChatScreen.
                navigate({
                    to: `/chat/${onlineDevice.device_id}`,
                    search: { initialMessage: content } as any
                })
            } else {
                navigate({
                    to: '/devices',
                    search: { initialMessage: content } as any
                } as any)
                toast.info("Please select a device to continue")
            }
        } catch (e) {
            navigate({ to: '/devices' as any })
        }
    }

    const handleProjectClick = async (project: any) => {
        // Switch project context
        setCurrentProject(project)
        setProjectInitialized(true)

        // Find a device for this project?
        // Ideally, we jump to the device that was last used for this project.
        // But we don't have that info easily.
        // Let's grep for online devices again.
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
        <div className="flex flex-col h-full bg-background relative overflow-hidden">
            {/* Background Decoration */}
            <div className="absolute top-0 left-0 w-full h-[50%] bg-gradient-to-b from-primary/5 to-transparent pointer-events-none" />

            {/* Top Right Search */}
            <div className="absolute top-4 right-4 z-20">
                <Button variant="ghost" size="icon" className="rounded-full hover:bg-muted" onClick={() => navigate({ to: '/search' as any })}>
                    <div className="w-10 h-10 bg-background/50 backdrop-blur-md rounded-full flex items-center justify-center shadow-sm border border-border/50">
                        <Search className="w-5 h-5 text-foreground" />
                    </div>
                </Button>
            </div>

            {/* Hero Section (Center) */}
            <div className="flex-1 flex flex-col items-center justify-center p-6 -mt-20 z-10">
                <div className="flex flex-col items-center mb-10 animate-in fade-in zoom-in duration-700">
                    <div className="mb-6 scale-150">
                        <Logo variant="icon" asLink={false} />
                    </div>
                    <h1 className="text-3xl font-bold text-foreground tracking-tight">
                        EvoLoop AI
                    </h1>
                    <p className="text-sm text-muted-foreground mt-2 font-medium">
                        Your Intelligent Mobile Agent
                    </p>
                </div>

                {/* Super Input */}
                <div className="w-full max-w-lg animate-in slide-in-from-bottom-8 duration-700 delay-100">
                    <ChatInput
                        isConnected={true} // Always enable on home
                        isDeviceOnline={true}
                        onSend={handleInputSend}
                        placeholder="Ask anything or command..."
                        className="w-full"
                        innerClassName="flex flex-col gap-3 bg-card/80 backdrop-blur-xl p-4 rounded-xl shadow-xl border border-primary/10 transition-all hover:shadow-2xl hover:border-primary/20"
                    />
                </div>
            </div>

            {/* Recent Projects (Bottom) */}
            <div className="shrink-0 pb-6 animate-in slide-in-from-bottom-12 duration-1000 delay-300">
                <div className="px-6 mb-3 flex items-center justify-between">
                    <h3 className="text-sm font-semibold text-muted-foreground flex items-center gap-1.5">
                        <Clock className="w-3.5 h-3.5" />
                        Recent Activities
                    </h3>
                    <Button variant="ghost" size="sm" className="h-6 text-xs hover:bg-transparent text-primary" onClick={() => navigate({ to: '/projects' as any })}>
                        View All
                    </Button>
                </div>

                <div className="flex overflow-x-auto px-6 gap-4 pb-4 scrollbar-hide snap-x">
                    {isLoading ? (
                        [1, 2, 3].map(i => (
                            <div key={i} className="w-48 h-32 shrink-0 bg-muted/40 rounded-2xl animate-pulse" />
                        ))
                    ) : recentProjects.length > 0 ? (
                        recentProjects.map((p: any) => (
                            <Card
                                key={p.project_id}
                                className="w-48 shrink-0 snap-start border-none bg-muted/30 hover:bg-muted/60 transition-colors cursor-pointer group"
                                onClick={() => handleProjectClick(p)}
                            >
                                <CardContent className="p-4 flex flex-col h-full justify-between gap-2">
                                    <div className="flex items-start justify-between">
                                        <div className="w-8 h-8 rounded-lg bg-background shadow-sm flex items-center justify-center text-[10px] font-bold text-primary">
                                            {p.project_name.substring(0, 2).toUpperCase()}
                                        </div>
                                        <div className="opacity-0 group-hover:opacity-100 transition-opacity">
                                            <ArrowRight className="w-4 h-4 text-muted-foreground" />
                                        </div>
                                    </div>
                                    <div>
                                        <h4 className="font-medium text-sm truncate">{p.project_name}</h4>
                                        <p className="text-[10px] text-muted-foreground truncate mt-0.5">
                                            {p.update_time ? new Date(p.update_time * 1000).toLocaleDateString() : 'Unknown'}
                                        </p>
                                    </div>
                                </CardContent>
                            </Card>
                        ))
                    ) : (
                        <div className="w-full text-center text-xs text-muted-foreground py-4 bg-muted/20 rounded-xl">
                            No recent projects found.
                        </div>
                    )}
                </div>
            </div>
        </div>
    )
}
