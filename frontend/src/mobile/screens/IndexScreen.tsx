import { useState } from "react"
import { Monitor, Search, Sparkles, FolderOpen, ArrowRight } from "lucide-react"
import { Input } from "@/components/ui/input"
import { Button } from "@/components/ui/button"
import { Card, CardContent } from "@/components/ui/card"
import { useNavigate } from "@tanstack/react-router"
import { useQuery } from "@tanstack/react-query"
import { EvoLoopApi } from "@/client/evoloopClient"

export function IndexScreen() {
    const navigate = useNavigate()
    const [mode, setMode] = useState<'chat' | 'search'>('chat')
    const [inputText, setInputText] = useState("")

    // Fetch Recent Projects (using list for now, ideally recent API)
    const { data: projectsData, isLoading } = useQuery({
        queryKey: ['evoloop', 'projects', 'recent'],
        queryFn: () => EvoLoopApi.getCloudProjects({ page: 1, page_size: 5 }), // Top 5
    })
    const recentProjects = projectsData?.list || []

    const handleAction = () => {
        if (!inputText.trim()) return

        if (mode === 'search') {
            navigate({
                to: '/search',
                search: { keyword: inputText }
            } as any)
        } else {
            // Chat mode: Find first device or ask to select?
            // "Conversation mode" - Usually implies starting a chat. 
            // If we have a stored last device, go there? Or general intent?
            // For now, let's navigate to devices list if generic, or search if typed?
            // Or maybe this input IS just a fancy jumping point.
            // Requirement said "input box (switchable dialogue / search mode)".
            // If dialogue, maybe send command to *current* context? But Home has no context.
            // Let's make it intuitive: "Chat" mode -> Navigate to Device Selection or Chat if One exists.
            // Let's assume navigating to Devices for now, with text passed?
            // Actually, maybe just navigate to /devices with a toast "Select a device to chat".
            // BETTER: Prompt user to pick a device.
            navigate({ to: '/devices' as any })
        }
    }

    return (
        <div className="flex flex-col h-full bg-background p-4 gap-6">
            {/* Logo Section */}
            <div className="flex flex-col items-center justify-center pt-8 pb-4 animate-in fade-in zoom-in duration-500">
                <div className="w-16 h-16 bg-primary/10 rounded-2xl flex items-center justify-center mb-3 shadow-sm">
                    <Monitor className="w-8 h-8 text-primary" />
                </div>
                <h1 className="text-2xl font-bold bg-clip-text text-transparent bg-gradient-to-r from-primary to-blue-600">
                    EvoLoop
                </h1>
                <p className="text-xs text-muted-foreground tracking-widest mt-1">MOBILE AGENT</p>
            </div>

            {/* Input Section */}
            <div className="w-full max-w-md mx-auto relative animate-in slide-in-from-bottom-4 duration-500 delay-100">
                {/* Mode Switcher */}
                <div className="absolute -top-3 left-4 bg-background px-1 z-10 flex gap-2">
                    <button
                        onClick={() => setMode('chat')}
                        className={`text-xs font-medium px-2 py-0.5 rounded-full transition-colors ${mode === 'chat' ? 'bg-primary/10 text-primary' : 'text-muted-foreground hover:bg-muted'}`}
                    >
                        Chat
                    </button>
                    <button
                        onClick={() => setMode('search')}
                        className={`text-xs font-medium px-2 py-0.5 rounded-full transition-colors ${mode === 'search' ? 'bg-primary/10 text-primary' : 'text-muted-foreground hover:bg-muted'}`}
                    >
                        Search
                    </button>
                </div>

                <div className="relative">
                    <div className="absolute left-3 top-3 text-muted-foreground">
                        {mode === 'chat' ? <Sparkles className="w-5 h-5" /> : <Search className="w-5 h-5" />}
                    </div>
                    <Input
                        placeholder={mode === 'chat' ? "Ask AI Assistant..." : "Search logs..."}
                        className="pl-10 h-12 text-base rounded-xl shadow-sm border-muted-foreground/20 focus-visible:ring-primary/20"
                        value={inputText}
                        onChange={(e) => setInputText(e.target.value)}
                        onKeyDown={(e) => e.key === 'Enter' && handleAction()}
                    />
                    {inputText && (
                        <Button
                            className="absolute right-1 top-1 h-10 w-10 p-0 rounded-lg"
                            size="icon"
                            onClick={handleAction}
                        >
                            <ArrowRight className="w-5 h-5" />
                        </Button>
                    )}
                </div>
            </div>

            {/* Recent Projects */}
            <div className="flex-1 overflow-hidden flex flex-col pt-2 animate-in slide-in-from-bottom-8 duration-700 delay-200">
                <div className="flex items-center justify-between mb-3 px-1">
                    <h2 className="font-semibold text-lg flex items-center gap-2">
                        <FolderOpen className="w-4 h-4 text-primary" />
                        Recent Projects
                    </h2>
                    <Button variant="ghost" className="text-xs h-6 px-2 text-muted-foreground" onClick={() => navigate({ to: '/projects' as any })}>
                        View All
                    </Button>
                </div>

                <div className="flex-1 overflow-y-auto space-y-3 pb-20"> {/* pb-20 for bottom nav clearance */}
                    {isLoading ? (
                        [1, 2, 3].map(i => (
                            <div key={i} className="h-16 bg-muted/50 rounded-xl animate-pulse" />
                        ))
                    ) : recentProjects.length > 0 ? (
                        recentProjects.map((p: any) => (
                            <Card
                                key={p.project_id}
                                className="border-none bg-muted/30 hover:bg-accent transition-colors cursor-pointer active:scale-[0.99] transition-transform"
                                onClick={() => navigate({ to: '/projects' as any })} // Ideally navigate to project detail? Or just list for now.
                            >
                                <CardContent className="p-3 flex items-center gap-3">
                                    <div className="w-10 h-10 rounded-full bg-background flex items-center justify-center shrink-0 shadow-sm border border-border/50">
                                        <div className="text-xs font-bold text-primary max-w-full truncate px-1">
                                            {p.project_name.substring(0, 2).toUpperCase()}
                                        </div>
                                    </div>
                                    <div className="flex-1 min-w-0">
                                        <h3 className="font-medium truncate">{p.project_name}</h3>
                                        <p className="text-xs text-muted-foreground truncate">
                                            Last active: {p.update_time ? new Date(p.update_time * 1000).toLocaleDateString() : 'N/A'}
                                        </p>
                                    </div>
                                    <ArrowRight className="w-4 h-4 text-muted-foreground/50" />
                                </CardContent>
                            </Card>
                        ))
                    ) : (
                        <div className="text-center text-muted-foreground py-8 text-sm">
                            No recent projects.
                        </div>
                    )}
                </div>
            </div>
        </div>
    )
}
