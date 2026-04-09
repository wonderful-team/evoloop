import {
  FolderOpen,
  MessageSquare,
  Settings,
  ListTodo,
  GraduationCap,
  BookOpen,
} from "lucide-react"
import { useTranslation } from "react-i18next"
import { SidebarAppearance } from "@/components/Common/Appearance"
import { Logo } from "@evoloop/shared/components/Logo"
import {
  Sidebar,
  SidebarContent,
  SidebarFooter,
  SidebarHeader,
  useSidebar,
} from "@evoloop/shared/components/ui/sidebar"
import useAuth from "@/hooks/useAuth"
// 注意：Sidebar 不再根据权限过滤菜单，所有功能都显示
// 权限控制统一由后端处理，前端捕获错误后提示升级
import { type Item, Main } from "./Main"
import { User } from "./User"

export function AppSidebar() {
  const { t } = useTranslation()
  const { user: currentUser } = useAuth()
  const { toggleSidebar } = useSidebar()

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
    {
      icon: BookOpen,
      title: t("sidebar.knowledge"),
      path: "/knowledge",
      dataTour: "sidebar-knowledge",
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
        <User user={currentUser} />
      </SidebarFooter>
    </Sidebar>
  )
}

export default AppSidebar
