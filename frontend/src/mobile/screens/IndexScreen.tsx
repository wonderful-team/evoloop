import { Logo } from "@/components/Common/Logo"
import { useNavigate } from "@tanstack/react-router"
import { ChatInput } from "../components/chat/ChatInput"
import { toast } from "sonner"
// import { Menu } from "lucide-react"
// import { Button } from "@/components/ui/button"
// import { ConversationDrawer } from "../components/ConversationDrawer"

export function IndexScreen() {
    const navigate = useNavigate()
    const isGuest = !localStorage.getItem('evoloop_token')

    const handleInputSend = async (content: string) => {
        if (isGuest) {
            toast.info("Please login to continue")
            navigate({ to: '/login' as any })
            return
        }

        // Direct to Cloud Chat
        navigate({
            to: '/cloud-chat/new',
            search: { initialMessage: content } as any
        })
    }

    return (
        <div className="flex flex-col h-full bg-background relative overflow-hidden">
            {/* Background Decoration */}
            <div className="absolute top-0 left-0 w-full h-[50%] bg-gradient-to-b from-primary/5 to-transparent pointer-events-none" />

            {/* Header (Removed Drawer, clean header) */}
            <div className="absolute top-0 left-0 right-0 p-4 flex justify-between z-20">
                {/* Empty header for spacing if needed, or remove completely */}
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
                <div className="w-full max-w-lg mb-8 animate-in slide-in-from-bottom-8 duration-700 delay-100">
                    <ChatInput
                        isConnected={true}
                        isDeviceOnline={true}
                        onSend={handleInputSend}
                        placeholder="Ask anything or command..."
                        className="w-full"
                        innerClassName="flex flex-col gap-3 bg-card/80 backdrop-blur-xl p-4 rounded-xl shadow-xl border border-primary/10 transition-all hover:shadow-2xl hover:border-primary/20"
                    />
                </div>
            </div>
        </div>
    )
}
