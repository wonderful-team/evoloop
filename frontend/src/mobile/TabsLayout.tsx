import { Outlet, Link, useLocation, useNavigate } from "@tanstack/react-router"
import { Home, Monitor, FolderOpen, User, Cloud, Search } from "lucide-react"
import { useMobileStore } from "./stores/useMobileStore"
import { motion, useMotionValue, animate } from "framer-motion"
import { Button } from "@/components/ui/button"
import { useEffect, useRef } from "react"

// Import Screens directly for pre-loading side-by-side
import { IndexScreen } from "./screens/IndexScreen"
import { ProfileScreen } from "./screens/ProfileScreen"
import { DevicesScreen } from "./screens/DevicesScreen"
import { ProjectsScreen } from "./screens/ProjectsScreen"

export function TabsLayout() {
    const location = useLocation()
    const navigate = useNavigate()
    const path = location.pathname
    const { activeTab, setActiveTab } = useMobileStore()
    const x = useMotionValue(0)

    const isActive = (p: string) => {
        if (p === '/' && path === '/') return true
        if (p !== '/' && path.startsWith(p)) return true
        return false
    }

    const showLocalTabs = activeTab === 'local'

    // Sync State with URL (Bidirectional Sync)
    useEffect(() => {
        if (path === '/' || path.startsWith('/profile')) {
            if (activeTab !== 'cloud') setActiveTab('cloud')
            animate(x, 0, { type: "spring", stiffness: 300, damping: 30 })
        } else if (path.startsWith('/devices') || path.startsWith('/projects')) {
            if (activeTab !== 'local') setActiveTab('local')
            animate(x, -window.innerWidth, { type: "spring", stiffness: 300, damping: 30 })
        }
    }, [path])

    const handleTabSwitch = (tab: 'cloud' | 'local') => {
        if (tab === activeTab) return;
        if (tab === 'cloud') {
            navigate({ to: '/' as any });
        } else {
            navigate({ to: '/devices' as any });
        }
    }

    const handleDragEnd = (event: any, info: any) => {
        const offset = info.offset.x
        const velocity = info.velocity.x
        const width = window.innerWidth

        let targetTab = activeTab

        if (activeTab === 'cloud') {
            if (offset < -50 || velocity < -500) targetTab = 'local'
        } else {
            if (offset > 50 || velocity > 500) targetTab = 'cloud'
        }

        if (targetTab === 'cloud') {
            if (activeTab !== 'cloud') {
                navigate({ to: '/' as any })
            } else {
                animate(x, 0, { type: "spring", stiffness: 300, damping: 30 })
            }
        } else {
            if (activeTab !== 'local') {
                navigate({ to: '/devices' as any })
            } else {
                animate(x, -width, { type: "spring", stiffness: 300, damping: 30 })
            }
        }
    }

    // Manual Routing for Cloud Container
    const renderCloudContent = () => {
        if (path.startsWith('/profile')) return <ProfileScreen />
        return <IndexScreen />
    }

    // Manual Routing for Local Container
    const renderLocalContent = () => {
        if (path.startsWith('/projects')) return <ProjectsScreen />
        return <DevicesScreen />
    }

    return (
        <div className="flex flex-col h-screen bg-background text-foreground relative overflow-hidden">
            {/* Top Global Header with Safe Area Fix */}
            {/* Added extra padding (pt-6) to existing safe-top to avoid overlay overlap */}
            <div className="absolute top-0 left-0 right-0 z-30 pt-safe-top pt-6 flex justify-center items-center h-16 pointer-events-none">
                <div className="flex bg-muted/50 rounded-full p-1 relative backdrop-blur-md pointer-events-auto shadow-sm border border-border/50">
                    <motion.div
                        className="absolute top-1 bottom-1 bg-background shadow-sm rounded-full"
                        initial={false}
                        animate={{
                            left: activeTab === 'cloud' ? 4 : '50%',
                            width: 'calc(50% - 4px)'
                        }}
                        transition={{ type: "spring", stiffness: 300, damping: 30 }}
                    />
                    <button
                        onClick={() => handleTabSwitch('cloud')}
                        className={`relative z-10 px-6 py-1 text-sm font-medium transition-colors ${activeTab === 'cloud' ? 'text-primary' : 'text-muted-foreground'}`}
                    >
                        Cloud
                    </button>
                    <button
                        onClick={() => handleTabSwitch('local')}
                        className={`relative z-10 px-6 py-1 text-sm font-medium transition-colors ${activeTab === 'local' ? 'text-primary' : 'text-muted-foreground'}`}
                    >
                        Local
                    </button>
                </div>
                <div className="absolute right-4 top-1/2 -translate-y-1/2 mt-3 pointer-events-auto">
                    {activeTab === 'local' && (
                        <Button variant="ghost" size="icon" className="h-9 w-9 rounded-full bg-background/50 backdrop-blur-md border border-border/50 shadow-sm" onClick={() => navigate({ to: '/search' as any })}>
                            <Search className="w-4 h-4 text-muted-foreground" />
                        </Button>
                    )}
                </div>
            </div>

            {/* Gesture Container (Real-time Swipe) */}
            <motion.div
                className="flex-1 flex w-[200vw] h-full"
                style={{ x, touchAction: "pan-y" }}
                drag="x"
                dragConstraints={{ left: -window.innerWidth, right: 0 }}
                dragElastic={0.1}
                onDragEnd={handleDragEnd}
            >
                {/* Cloud Context Container */}
                <div className="w-[100vw] h-full pt-20 overflow-y-auto no-scrollbar relative">
                    {renderCloudContent()}
                </div>

                {/* Local Context Container */}
                <div className="w-[100vw] h-full pt-20 overflow-y-auto no-scrollbar relative">
                    {renderLocalContent()}
                </div>
            </motion.div>


            {/* Bottom Tab Bar */}
            <div className="border-t bg-background/80 backdrop-blur-md pb-safe absolute bottom-0 w-full z-40">
                <div className="flex justify-around items-center h-14 px-2">
                    {/* Cloud Tabs */}
                    <div className={`flex justify-around w-full ${showLocalTabs ? 'hidden' : 'flex'}`}>
                        <Link to={"/" as any} className={`flex flex-col items-center gap-1 w-16 transition-colors ${isActive('/') ? 'text-primary' : 'text-muted-foreground'}`}>
                            <Home className="w-5 h-5" />
                            <span className="text-[10px] font-medium">Home</span>
                        </Link>
                        <Link to={"/profile" as any} className={`flex flex-col items-center gap-1 w-16 transition-colors ${isActive('/profile') ? 'text-primary' : 'text-muted-foreground'}`}>
                            <User className="w-5 h-5" />
                            <span className="text-[10px] font-medium">Me</span>
                        </Link>
                    </div>

                    {/* Local Tabs */}
                    <div className={`flex justify-around w-full ${!showLocalTabs ? 'hidden' : 'flex'}`}>
                        <Link to={"/devices" as any} className={`flex flex-col items-center gap-1 w-16 transition-colors ${isActive('/devices') ? 'text-primary' : 'text-muted-foreground'}`}>
                            <Monitor className="w-5 h-5" />
                            <span className="text-[10px] font-medium">Devices</span>
                        </Link>
                        <Link to={"/projects" as any} className={`flex flex-col items-center gap-1 w-16 transition-colors ${isActive('/projects') ? 'text-primary' : 'text-muted-foreground'}`}>
                            <FolderOpen className="w-5 h-5" />
                            <span className="text-[10px] font-medium">Projects</span>
                        </Link>
                    </div>
                </div>
            </div>
        </div>
    )
}
