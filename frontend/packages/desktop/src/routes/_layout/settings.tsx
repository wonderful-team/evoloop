import i18n from "@evoloop/shared/i18n"
import { cn } from "@evoloop/shared/lib/utils"
import { createFileRoute, redirect } from "@tanstack/react-router"
import {
  AlertTriangle,
  Brain,
  Mic,
  Palette,
  Settings,
  User,
} from "lucide-react"
import { useEffect, useState } from "react"
import { useTranslation } from "react-i18next"
import GeneralSettings from "@/components/Settings/GeneralSettings"
import { ModelSettings } from "@/components/Settings/ModelSettings"
import { VoiceControlSettings } from "@/components/Settings/VoiceControlSettings"
import { AccountSettings } from "@/components/UserSettings/AccountSettings"
import AppearanceSettings from "@/components/UserSettings/AppearanceSettings"
import DeleteAccount from "@/components/UserSettings/DeleteAccount"
import useAuth, { isLoggedIn } from "@/hooks/useAuth"
import { isTauri } from "@/lib/tauri"

const NavConfig = () => {
  const { t } = useTranslation()
  const items = [
    {
      value: "general",
      title: t("settings.tabs.general"),
      icon: Settings,
      component: GeneralSettings,
    },
    {
      value: "models",
      title: t("settings.tabs.models"),
      icon: Brain,
      component: ModelSettings,
    },
    {
      value: "voice",
      title: t("settings.tabs.voice"),
      icon: Mic,
      component: VoiceControlSettings,
    },
    {
      value: "account",
      title: t("settings.tabs.profile"),
      icon: User,
      component: AccountSettings,
    },
    {
      value: "appearance",
      title: t("settings.tabs.appearance"),
      icon: Palette,
      component: AppearanceSettings,
    },
    {
      value: "danger-zone",
      title: t("settings.tabs.danger"),
      icon: AlertTriangle,
      component: DeleteAccount,
      variant: "danger" as const,
    },
  ]
  if (!isTauri()) {
    return items.filter(
      (item) => item.value !== "models" && item.value !== "voice",
    )
  }
  return items
}

export const Route = createFileRoute("/_layout/settings")({
  component: UserSettings,
  beforeLoad: async () => {
    if (!isLoggedIn()) {
      throw redirect({ to: "/login" })
    }
  },
  head: () => ({
    meta: [
      {
        title: i18n.t("settings.pageTitle"),
      },
    ],
  }),
})

import { SettingsActionBar } from "@/components/Settings/SettingsActionBar"
import { SettingsProvider } from "@/components/Settings/SettingsContext"

function UserSettings() {
  const { t } = useTranslation()
  const [activeTab, setActiveTab] = useState("general")

  useEffect(() => {
    document.title = t("settings.pageTitle")
  }, [t])

  const { user: currentUser } = useAuth()
  const navItems = NavConfig()
  const ActiveComponent =
    navItems.find((item) => item.value === activeTab)?.component ||
    GeneralSettings

  if (!currentUser) {
    return null
  }

  return (
    <SettingsProvider>
      <div className="flex h-full flex-col gap-8 relative pb-20">
        <div>
          <h1 className="text-3xl font-bold tracking-tight">
            {t("settings.title")}
          </h1>
          <p className="text-muted-foreground mt-1">{t("settings.intro")}</p>
        </div>

        <div className="flex flex-1 flex-col gap-8 md:flex-row">
          <aside className="w-full md:w-64 shrink-0">
            <nav className="flex flex-col gap-1">
              {navItems.map((item) => {
                const Icon = item.icon
                const isActive = activeTab === item.value
                return (
                  <button
                    key={item.value}
                    onClick={() => setActiveTab(item.value)}
                    className={cn(
                      "group flex items-center gap-3 rounded-md px-3 py-2 text-sm font-medium transition-all duration-200",
                      isActive
                        ? "bg-primary text-primary-foreground"
                        : "text-muted-foreground hover:bg-muted hover:text-foreground",
                      item.variant === "danger" &&
                        !isActive &&
                        "hover:bg-destructive/10 hover:text-destructive",
                    )}
                  >
                    <Icon
                      className={cn(
                        "h-4 w-4 transition-transform group-hover:scale-110",
                        isActive
                          ? "text-primary-foreground"
                          : "text-muted-foreground",
                        item.variant === "danger" &&
                          !isActive &&
                          "group-hover:text-destructive",
                      )}
                    />
                    {item.title}
                  </button>
                )
              })}
            </nav>
          </aside>

          <main className="flex-1 min-w-0">
            <div className="animate-in fade-in slide-in-from-right-4 duration-300">
              <ActiveComponent />
            </div>
          </main>
        </div>

        <SettingsActionBar />
      </div>
    </SettingsProvider>
  )
}

export default UserSettings
