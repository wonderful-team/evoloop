
import { Logo } from "@/components/Common/Logo"
// import { Button } from "@/components/ui/button"
import { useNavigate } from "@tanstack/react-router"
import { ChatInput } from "../components/chat/ChatInput"
// import { useMobileStore } from "../stores/useMobileStore" // unused
import { toast } from "sonner"
import { EvoLoopApi } from "@/client/evoloopClient"

export function IndexScreen() {
    const navigate = useNavigate()
    // const { } = useMobileStore() // unused

    const isGuest = !localStorage.getItem('evoloop_token')

    const handleInputSend = async (content: string) => {
        if (isGuest) {
            toast.info("Please login to continue")
            navigate({ to: '/login' as any })
            return
        }

        try {
            const devices = await EvoLoopApi.getDeviceList();
            const onlineDevice = devices.find(d => d.status === 1);

            if (onlineDevice) {
                navigate({
                    to: `/chat/${onlineDevice.device_id}`,
                    search: { initialMessage: content } as any
                })
            } else {
                if (devices.length > 0) {
                    navigate({
                        to: `/chat/${devices[0].device_id}`,
                        search: { initialMessage: content } as any
                    })
                } else {
                    navigate({
                        to: '/devices',
                        search: { initialMessage: content } as any
                    } as any)
                    toast.info("Please select a device to continue")
                }
            }
        } catch (e) {
            navigate({ to: '/devices' as any })
        }
    }

    return (
        <div className="flex flex-col h-full bg-background relative overflow-hidden">
            {/* Background Decoration */}
            <div className="absolute top-0 left-0 w-full h-[50%] bg-gradient-to-b from-primary/5 to-transparent pointer-events-none" />

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
