import { Button } from "@/components/ui/button"
import { EvoLoopApi } from "@/client/evoloopClient"
import { useNavigate } from "@tanstack/react-router"
import { LogOut, User } from "lucide-react"

export function ProfileScreen() {
    const navigate = useNavigate()

    const handleLogout = () => {
        EvoLoopApi.logout()
        navigate({ to: '/login' })
    }

    return (
        <div className="p-4 flex flex-col h-full">
            <h1 className="text-xl font-bold mb-6">Profile</h1>
            <div className="flex-1 flex flex-col items-center justify-center gap-4 text-muted-foreground">
                <div className="w-20 h-20 bg-muted rounded-full flex items-center justify-center">
                    <User className="w-10 h-10" />
                </div>
                <p>User Profile</p>
            </div>
            <Button variant="destructive" className="w-full gap-2" onClick={handleLogout}>
                <LogOut className="w-4 h-4" />
                Logout
            </Button>
        </div>
    )
}
