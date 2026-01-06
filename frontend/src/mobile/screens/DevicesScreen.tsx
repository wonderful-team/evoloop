import { useQuery } from "@tanstack/react-query"
import { redirect, useNavigate } from "@tanstack/react-router"
import { Activity, Monitor, Smartphone } from "lucide-react"
import { Trans, useTranslation } from "react-i18next"
import { DevicesService } from "@/client/sdk.gen"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import {
  Card,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card"

export async function devicesLoader() {
  const token = localStorage.getItem("evoloop_token")
  if (!token) {
    throw redirect({ to: "/login" as any })
  }
}

export function DevicesScreen() {
  const { t } = useTranslation()
  const navigate = useNavigate()
  const token = localStorage.getItem("evoloop_token")
  const isGuest = !token

  const {
    data: devices,
    isLoading,
    error,
  } = useQuery({
    queryKey: ["evoloop", "devices"],
    queryFn: async () => {
      const res: any = await DevicesService.getDevices()
      // Backend returns { code: 0, data: [...] } or just array?
      // ImagicBoxClient.get_devices returns result of _request which returns response.json()
      // _request returns { code: ..., data: ... } usually for Member Center APIs.
      // Let's handle both cases validly
      if (Array.isArray(res)) return res
      if (res && Array.isArray(res.data)) return res.data
      return []
    },
    refetchInterval: 5000,
    retry: false,
    enabled: !!token,
  })

  // Remove auto-logout effect to allow guest view
  // useEffect(() => { ... })

  const onlineCount = devices?.filter((d) => d.status === 1).length || 0

  if (isGuest) {
    return (
      <div className="p-4 space-y-4 h-full flex flex-col">
        <div className="flex items-center justify-between">
          <h1 className="text-2xl font-bold tracking-tight">
            {t("devices.title")}
          </h1>
        </div>

        <div className="flex-1 flex flex-col items-center justify-center space-y-6 text-center animate-in fade-in slide-in-from-bottom-4 duration-700">
          <div className="w-20 h-20 bg-muted/50 rounded-full flex items-center justify-center">
            <Monitor className="w-10 h-10 text-muted-foreground/50" />
          </div>
          <div className="max-w-xs space-y-2">
            <h3 className="text-lg font-semibold">
              {t("devices.guestTitle") || "Login to View Devices"}
            </h3>
            <p className="text-sm text-muted-foreground">
              {t("devices.guestDesc") ||
                "Access your remote devices and control them from anywhere."}
            </p>
          </div>
          <div className="flex gap-3 w-full max-w-xs">
            <Button
              className="flex-1"
              onClick={() => navigate({ to: "/login" as any })}
            >
              {t("auth.login.submit")}
            </Button>
            <Button
              variant="outline"
              className="flex-1"
              onClick={() => navigate({ to: "/register" as any })}
            >
              {t("auth.login.signUp")}
            </Button>
          </div>
        </div>
      </div>
    )
  }

  return (
    <div className="p-4 space-y-4">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">
            {t("devices.title")}
          </h1>
          <p className="text-sm text-muted-foreground">
            {isLoading
              ? t("devices.loading")
              : t("devices.statusFormat", {
                  online: onlineCount,
                  total: devices?.length || 0,
                })}
          </p>
        </div>
      </div>

      {error ? (
        <div className="p-4 bg-destructive/15 text-destructive rounded-md">
          {t("devices.errorLoading")} {(error as any).message}
        </div>
      ) : null}

      <div className="grid gap-3">
        {devices?.map((device) => (
          <Card
            key={device.device_id}
            className={`border-l-4 ${device.status === 1 ? "border-l-green-500" : "border-l-muted"} active:scale-95 transition-transform`}
            onClick={() => navigate({ to: `/chat/${device.device_id}` as any })}
          >
            <CardHeader className="p-4 pb-2">
              <div className="flex justify-between items-start">
                <div className="flex items-center gap-2">
                  {device.os_info.toLowerCase().includes("phone") ? (
                    <Smartphone className="h-5 w-5 text-muted-foreground" />
                  ) : (
                    <Monitor className="h-5 w-5 text-muted-foreground" />
                  )}
                  <CardTitle className="text-base">
                    {device.device_name}
                  </CardTitle>
                </div>
                <Badge variant={device.status === 1 ? "default" : "secondary"}>
                  {device.status === 1
                    ? t("devices.online")
                    : t("devices.offline")}
                </Badge>
              </div>
              <CardDescription className="text-xs">
                {device.os_info || t("devices.unknownOS")}
                {device.status === 1 && (
                  <span className="ml-2 text-green-600 dark:text-green-400 text-xs flex items-center inline-flex gap-1">
                    <Activity className="h-3 w-3" /> {t("devices.active")}
                  </span>
                )}
              </CardDescription>
            </CardHeader>
          </Card>
        ))}

        {!isLoading && devices?.length === 0 && (
          <div className="py-4">
            <Card className="bg-primary/5 border-primary/20 shadow-sm">
              <CardHeader>
                <div className="flex items-center gap-3 mb-2">
                  <div className="w-10 h-10 rounded-full bg-primary/10 flex items-center justify-center">
                    <Monitor className="w-5 h-5 text-primary" />
                  </div>
                  <CardTitle>{t("devices.connectFirst")}</CardTitle>
                </div>
                <CardDescription className="text-sm leading-relaxed">
                  {t("devices.connectDesc")}
                </CardDescription>
              </CardHeader>
              <div className="px-6 pb-6 space-y-4">
                <ol className="list-decimal list-inside text-sm text-muted-foreground space-y-1">
                  <li>
                    <Trans i18nKey="devices.step1">
                      Visit{" "}
                      <span className="text-foreground font-medium select-all">
                        develop-assistant.cn
                      </span>{" "}
                      on your computer
                    </Trans>
                  </li>
                  <li>{t("devices.step2")}</li>
                  <li>{t("devices.step3")}</li>
                </ol>
                <Button
                  className="w-full gap-2"
                  variant="outline"
                  onClick={() => {
                    navigator.clipboard.writeText(
                      "https://develop-assistant.cn/download",
                    )
                    // Assuming toast is available or just let user know
                    alert(t("devices.linkCopied"))
                  }}
                >
                  {t("devices.copyLink")}
                  <Activity className="w-4 h-4" />
                </Button>
              </div>
            </Card>
          </div>
        )}
      </div>
    </div>
  )
}
