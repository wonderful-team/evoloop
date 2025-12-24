import { Outlet, Link, useLocation } from "@tanstack/react-router"
import { Home, Monitor, FolderOpen, User } from "lucide-react"

export function TabsLayout() {
    const location = useLocation()
    const path = location.pathname

    const isActive = (p: string) => {
        if (p === '/' && path === '/') return true
        if (p !== '/' && path.startsWith(p)) return true
        return false
    }

    return (
        <div className="flex flex-col h-screen bg-background text-foreground">
            <div className="flex-1 overflow-hidden">
                <Outlet />
            </div>
            {/* Bottom Tab Bar */}
            <div className="border-t bg-background/80 backdrop-blur-md pb-safe">
                <div className="flex justify-around items-center h-14">
                    <Link to={"/" as any} className={`flex flex-col items-center gap-1 w-16 ${isActive('/') ? 'text-primary' : 'text-muted-foreground'}`}>
                        <Home className="w-5 h-5" />
                        <span className="text-[10px] font-medium">Home</span>
                    </Link>
                    <Link to={"/devices" as any} className={`flex flex-col items-center gap-1 w-16 ${isActive('/devices') ? 'text-primary' : 'text-muted-foreground'}`}>
                        <Monitor className="w-5 h-5" />
                        <span className="text-[10px] font-medium">Devices</span>
                    </Link>
                    <Link to={"/projects" as any} className={`flex flex-col items-center gap-1 w-16 ${isActive('/projects') ? 'text-primary' : 'text-muted-foreground'}`}>
                        <FolderOpen className="w-5 h-5" />
                        <span className="text-[10px] font-medium">Projects</span>
                    </Link>
                    <Link to={"/profile" as any} className={`flex flex-col items-center gap-1 w-16 ${isActive('/profile') ? 'text-primary' : 'text-muted-foreground'}`}>
                        <User className="w-5 h-5" />
                        <span className="text-[10px] font-medium">Me</span>
                    </Link>
                </div>
            </div>
        </div>
    )
}
