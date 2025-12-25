import React, { useEffect, useState } from "react"
import { useQuery } from "@tanstack/react-query"
import { SystemService, type SystemConfig } from "@/client"
import {
    AlertDialog,
    AlertDialogContent,
    AlertDialogDescription,
    AlertDialogHeader,
    AlertDialogTitle,
} from "@/components/ui/alert-dialog"
import GeneralSettings from "@/components/Settings/GeneralSettings"
import useAuth from "@/hooks/useAuth"

export default function InitializationCheck({ children }: { children: React.ReactNode }) {
    const { user } = useAuth()
    const [open, setOpen] = useState(false)

    const { data: config, isLoading } = useQuery({
        queryKey: ["systemConfig"],
        queryFn: () => SystemService.getSystemConfig(),
        enabled: !!user,
    })

    useEffect(() => {
        if (!isLoading && config) {
            const configMap: Record<string, string> = {}
                ; (config as unknown as SystemConfig[]).forEach((item) => {
                    configMap[item.key] = item.value
                })

            // Check if critical configs are missing
            const missingProjectsRoot = !configMap.PROJECTS_ROOT

            if (missingProjectsRoot) {
                setOpen(true)
            } else {
                setOpen(false)
            }
        }
    }, [config, isLoading])



    // If loading, we just show children or a loader.
    // Showing children might briefly flash improper state, but better than blocking.
    if (isLoading) return <>{children}</>

    return (
        <>
            {children}
            <AlertDialog open={open}>
                <AlertDialogContent className="max-w-3xl">
                    <AlertDialogHeader>
                        <AlertDialogTitle>System Integration Required</AlertDialogTitle>
                        <AlertDialogDescription>
                            Please configure the following system settings to proceed.
                        </AlertDialogDescription>
                    </AlertDialogHeader>

                    <div className="py-4">
                        <GeneralSettings />
                    </div>

                </AlertDialogContent>
            </AlertDialog>
        </>
    )
}
