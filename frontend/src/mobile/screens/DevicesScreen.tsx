import { useNavigate, redirect } from "@tanstack/react-router"
import { useQuery } from "@tanstack/react-query"
import { EvoLoopApi } from "@/client/evoloopClient"
import { Monitor, Smartphone, Activity, LogOut } from "lucide-react"
import { useEffect } from "react"
import { Card, CardHeader, CardTitle, CardDescription } from "@/components/ui/card"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"

export async function devicesLoader() {
    const token = localStorage.getItem('evoloop_token')
    if (!token) {
        throw redirect({ to: '/login' as any })
    }
}

export function DevicesScreen() {
    const navigate = useNavigate()

    const { data: devices, isLoading, error } = useQuery({
        queryKey: ['evoloop', 'devices'],
        queryFn: EvoLoopApi.getDeviceList,
        refetchInterval: 5000,
        retry: false,
    })

    // Handle error side effect
    useEffect(() => {
        if (error) {
            localStorage.removeItem('evoloop_token');
            navigate({ to: '/login' as any });
        }
    }, [error, navigate]);

    // Group devices if needed, for now just list
    const onlineCount = devices?.filter(d => d.status === 1).length || 0

    return (
        <div className="p-4 space-y-4">
            <div className="flex items-center justify-between">
                <div>
                    <h1 className="text-2xl font-bold tracking-tight">Devices</h1>
                    <p className="text-sm text-muted-foreground">
                        {isLoading ? "Loading..." : `${onlineCount} Online / ${devices?.length || 0} Total`}
                    </p>
                </div>
                <Button variant="ghost" size="icon" onClick={() => { localStorage.removeItem('evoloop_token'); navigate({ to: '/login' as any }) }}>
                    <LogOut className="h-5 w-5 text-muted-foreground" />
                </Button>
            </div>

            {error ? (
                <div className="p-4 bg-destructive/15 text-destructive rounded-md">
                    Error loading devices: {(error as any).message}
                </div>
            ) : null}

            <div className="grid gap-3">
                {devices?.map((device) => (
                    <Card
                        key={device.device_id}
                        className={`border-l-4 ${device.status === 1 ? 'border-l-green-500' : 'border-l-muted'} active:scale-95 transition-transform`}
                        onClick={() => navigate({ to: `/chat/${device.device_id}` as any })}
                    >
                        <CardHeader className="p-4 pb-2">
                            <div className="flex justify-between items-start">
                                <div className="flex items-center gap-2">
                                    {device.os_info.toLowerCase().includes('phone') ?
                                        <Smartphone className="h-5 w-5 text-muted-foreground" /> :
                                        <Monitor className="h-5 w-5 text-muted-foreground" />
                                    }
                                    <CardTitle className="text-base">{device.device_name}</CardTitle>
                                </div>
                                <Badge variant={device.status === 1 ? "default" : "secondary"}>
                                    {device.status === 1 ? "Online" : "Offline"}
                                </Badge>
                            </div>
                            <CardDescription className="text-xs">
                                {device.os_info || "Unknown OS"}
                                {device.status === 1 && <span className="ml-2 text-green-600 dark:text-green-400 text-xs flex items-center inline-flex gap-1"><Activity className="h-3 w-3" /> Active</span>}
                            </CardDescription>
                        </CardHeader>
                    </Card>
                ))}

                {!isLoading && devices?.length === 0 && (
                    <div className="text-center py-10 text-muted-foreground">
                        No devices found. Run the PC client to register one.
                    </div>
                )}
            </div>
        </div>
    )
}
