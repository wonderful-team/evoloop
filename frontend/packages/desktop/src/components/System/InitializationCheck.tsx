import { useQuery } from "@tanstack/react-query"
import type React from "react"
import { useEffect, useState } from "react"
import { useTranslation } from "react-i18next"
import { type SystemConfig, SystemService } from "@/client"
import GeneralSettings from "@/components/Settings/GeneralSettings"
import {
  AlertDialog,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@evoloop/shared/components/ui/alert-dialog"
import useAuth from "@/hooks/useAuth"

export default function InitializationCheck({
  children,
}: {
  children: React.ReactNode
}) {
  const { t } = useTranslation()
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
            <AlertDialogTitle>{t("system.initializationTitle")}</AlertDialogTitle>
            <AlertDialogDescription>
              {t("system.initializationDesc")}
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
