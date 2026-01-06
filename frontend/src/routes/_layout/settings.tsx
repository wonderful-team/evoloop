import { createFileRoute } from "@tanstack/react-router"
import { useTranslation } from "react-i18next"
import GeneralSettings from "@/components/Settings/GeneralSettings"
import { ModelSettings } from "@/components/Settings/ModelSettings"
import AppearanceSettings from "@/components/UserSettings/AppearanceSettings"
import ChangePassword from "@/components/UserSettings/ChangePassword"
import DeleteAccount from "@/components/UserSettings/DeleteAccount"
import UserInformation from "@/components/UserSettings/UserInformation"
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs"
import useAuth from "@/hooks/useAuth"

const TabsConfig = () => {
  const { t } = useTranslation()
  return [
    {
      value: "general",
      title: t("settings.tabs.general"),
      component: GeneralSettings,
    },
    {
      value: "models",
      title: t("settings.tabs.models"),
      component: ModelSettings,
    },
    {
      value: "my-profile",
      title: t("settings.tabs.profile"),
      component: UserInformation,
    },
    {
      value: "password",
      title: t("settings.tabs.password"),
      component: ChangePassword,
    },
    {
      value: "appearance",
      title: t("settings.tabs.appearance"),
      component: AppearanceSettings,
    },
    {
      value: "danger-zone",
      title: t("settings.tabs.danger"),
      component: DeleteAccount,
    },
  ]
}

export const Route = createFileRoute("/_layout/settings")({
  component: UserSettings,
  head: () => ({
    meta: [
      {
        title: "Settings - EvoLoop",
      },
    ],
  }),
})

function UserSettings() {
  const { t } = useTranslation()
  const { user: currentUser } = useAuth()
  // All users have access to all tabs
  const finalTabs = TabsConfig()

  if (!currentUser) {
    return null
  }

  return (
    <div className="flex flex-col gap-6">
      <div>
        <h1 className="text-2xl font-bold tracking-tight">
          {t("settings.title")}
        </h1>
        <p className="text-muted-foreground">{t("settings.intro")}</p>
      </div>

      <Tabs defaultValue="general">
        <TabsList>
          {finalTabs.map((tab) => (
            <TabsTrigger key={tab.value} value={tab.value}>
              {tab.title}
            </TabsTrigger>
          ))}
        </TabsList>
        {finalTabs.map((tab) => (
          <TabsContent key={tab.value} value={tab.value}>
            <tab.component />
          </TabsContent>
        ))}
      </Tabs>
    </div>
  )
}
