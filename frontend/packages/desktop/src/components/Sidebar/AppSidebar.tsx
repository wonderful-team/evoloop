import { Logo } from "@evoloop/shared/components/Logo"
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from "@evoloop/shared/components/ui/popover"
import {
  Sidebar,
  SidebarContent,
  SidebarFooter,
  SidebarHeader,
  SidebarMenu,
  SidebarMenuButton,
  SidebarMenuItem,
  useSidebar,
} from "@evoloop/shared/components/ui/sidebar"
import {
  Bug,
  FolderOpen,
  GraduationCap,
  MessageSquare,
  Settings,
} from "lucide-react"
import React from "react"
import { useTranslation } from "react-i18next"
import { DebugManagerPanel } from "@/components/Chat/DebugManager"
import { SidebarAppearance } from "@/components/Common/Appearance"
import useAuth from "@/hooks/useAuth"

import { type Item, Main } from "./Main"
import { User } from "./User"

function AppSidebar() {
  const { t } = useTranslation()
  const { user: currentUser } = useAuth()
  const { toggleSidebar } = useSidebar()
  const [debugOpen, setDebugOpen] = React.useState(false)
  const isDev = import.meta.env.DEV

  const publicItems: Item[] = [
    {
      icon: MessageSquare,
      title: t("sidebar.chat"),
      path: "/chat",
      dataTour: "sidebar-chat",
    },
    {
      icon: FolderOpen,
      title: t("sidebar.projects"),
      path: "/projects",
      dataTour: "sidebar-projects",
    },
  ]

  const authItems: Item[] = [
    {
      icon: GraduationCap,
      title: t("sidebar.learning"),
      path: "/learning",
      dataTour: "sidebar-learning",
    },
    {
      icon: Settings,
      title: t("sidebar.settings"),
      path: "/settings",
      dataTour: "sidebar-settings",
    },
  ]

  const items = currentUser ? [...publicItems, ...authItems] : publicItems

  return (
    <Sidebar collapsible="icon">
      <SidebarHeader
        data-tauri-drag-region
        style={{ WebkitAppRegion: "drag" } as React.CSSProperties}
        className="pt-6 select-none"
      >
        <div
          className="flex h-12 cursor-pointer items-center justify-center py-2 transition-opacity hover:opacity-80"
          style={{ WebkitAppRegion: "no-drag" } as React.CSSProperties}
          onClick={toggleSidebar}
        >
          <Logo variant="responsive" />
        </div>
      </SidebarHeader>
      <SidebarContent
        style={{ WebkitAppRegion: "no-drag" } as React.CSSProperties}
      >
        <Main items={items} />
      </SidebarContent>
      <SidebarFooter
        style={{ WebkitAppRegion: "no-drag" } as React.CSSProperties}
      >
        <SidebarAppearance />
        {isDev && (
          <SidebarMenu>
            <SidebarMenuItem>
              <Popover open={debugOpen} onOpenChange={setDebugOpen}>
                <PopoverTrigger asChild>
                  <SidebarMenuButton
                    tooltip={t("sidebar.debugTooltip")}
                    isActive={debugOpen}
                    className="text-warning/70 hover:text-warning hover:bg-warning/10 data-[active=true]:bg-warning/10 data-[active=true]:text-warning"
                  >
                    <Bug className="h-4 w-4 shrink-0" />
                    <span>{t("sidebar.debug")}</span>
                  </SidebarMenuButton>
                </PopoverTrigger>
                <PopoverContent
                  side="right"
                  align="end"
                  className="w-[600px] h-[500px] p-0"
                >
                  <DebugManagerPanel onClose={() => setDebugOpen(false)} />
                </PopoverContent>
              </Popover>
            </SidebarMenuItem>
          </SidebarMenu>
        )}
        <User user={currentUser} />
      </SidebarFooter>
    </Sidebar>
  )
}

export default AppSidebar
