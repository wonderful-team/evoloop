import {
  FolderOpen,
  LayoutDashboard,
  MessageSquare,
  Server,
  Settings,
} from "lucide-react"
import { useTranslation } from "react-i18next"
import { SidebarAppearance } from "@/components/Common/Appearance"
import { Logo } from "@/components/Common/Logo"
import {
  Sidebar,
  SidebarContent,
  SidebarFooter,
  SidebarHeader,
} from "@/components/ui/sidebar"
import useAuth from "@/hooks/useAuth"
import { type Item, Main } from "./Main"
import { User } from "./User"

export function AppSidebar() {
  const { t } = useTranslation()
  const { user: currentUser } = useAuth()

  const publicItems: Item[] = [
    { icon: LayoutDashboard, title: t("sidebar.dashboard"), path: "/" },
    { icon: MessageSquare, title: t("sidebar.chat"), path: "/chat" },
    { icon: FolderOpen, title: t("sidebar.projects"), path: "/projects" },
  ]

  const authItems: Item[] = [
    { icon: Server, title: t("sidebar.mcpServers"), path: "/mcp" },
    { icon: Settings, title: t("sidebar.settings"), path: "/settings" },
  ]

  const items = currentUser ? [...publicItems, ...authItems] : publicItems

  return (
    <Sidebar collapsible="icon">
      <SidebarHeader>
        <div className="flex items-center justify-center py-2 h-12">
          <Logo variant="responsive" />
        </div>
      </SidebarHeader>
      <SidebarContent>
        <Main items={items} />
      </SidebarContent>
      <SidebarFooter>
        <SidebarAppearance />
        <User user={currentUser} />
      </SidebarFooter>
    </Sidebar>
  )
}

export default AppSidebar
