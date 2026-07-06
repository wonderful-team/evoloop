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
  ListTodo,
  MessageSquare,
  Settings,
} from "lucide-react"
import React from "react"
import { useTranslation } from "react-i18next"
import { DebugManagerPanel } from "@/components/Chat/DebugManager"
import { SidebarAppearance } from "@/components/Common/Appearance"
import useAuth from "@/hooks/useAuth"
// 注意：Sidebar 不再根据权限过滤菜单，所有功能都显示
// 权限控制统一由后端处理，前端捕获错误后提示升级
import { type Item, Main } from "./Main"
import { User } from "./User"

export function AppSidebar() {
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
    {
      icon: ListTodo,
      title: t("sidebar.todos"),
      path: "/todos",
      dataTour: "sidebar-todos",
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
      <SidebarHeader>
        <div
          className="flex h-12 cursor-pointer items-center justify-center py-2 transition-opacity hover:opacity-80"
          data-tour="sidebar-logo"
          onClick={toggleSidebar}
        >
          <Logo variant="responsive" />
        </div>
      </SidebarHeader>
      <SidebarContent>
        <Main items={items} />
      </SidebarContent>
      <SidebarFooter>
        <SidebarAppearance />
        {isDev && (
          <SidebarMenu>
            <SidebarMenuItem>
              <Popover open={debugOpen} onOpenChange={setDebugOpen}>
                <PopoverTrigger asChild>
                  <SidebarMenuButton
                    tooltip={t("sidebar.debugTooltip")}
                    isActive={debugOpen}
                    className="text-amber-500/70 hover:text-amber-400 hover:bg-amber-500/10 data-[active=true]:bg-amber-500/10 data-[active=true]:text-amber-400"
                  >
                    <Bug className="h-4 w-4 shrink-0" />
                    <span>{t("sidebar.debug")}</span>
                  </SidebarMenuButton>
                </PopoverTrigger>
                <PopoverContent
                  side="right"
                  align="end"
                  sideOffset={8}
                  className="w-auto p-0 bg-zinc-900/95 backdrop-blur-xl border border-white/10 shadow-2xl rounded-2xl"
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
