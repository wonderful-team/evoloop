import { Briefcase, Home, Users, FolderOpen, MessageSquare, Settings, Server, LayoutDashboard } from "lucide-react"


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

const baseItems: Item[] = [
  { icon: LayoutDashboard, title: "Dashboard", path: "/" },
  { icon: MessageSquare, title: "Chat", path: "/chat" },
  { icon: FolderOpen, title: "Projects", path: "/projects" },
  { icon: Server, title: "MCP Servers", path: "/mcp" },
  { icon: Settings, title: "Settings", path: "/settings" },
]

export function AppSidebar() {
  const { user: currentUser } = useAuth()

  const items = currentUser?.is_superuser
    ? [...baseItems, { icon: Users, title: "Admin", path: "/admin" }]
    : baseItems

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
