import { Link as RouterLink } from "@tanstack/react-router"
import { ChevronsUpDown, Crown, LifeBuoy, LogOut, Settings } from "lucide-react"
import { useTranslation } from "react-i18next"
import { Avatar, AvatarFallback } from "@evoloop/shared/components/ui/avatar"
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@evoloop/shared/components/ui/dropdown-menu"
import {
  SidebarMenu,
  SidebarMenuButton,
  SidebarMenuItem,
  useSidebar,
} from "@evoloop/shared/components/ui/sidebar"
import useAuth from "@/hooks/useAuth"
import { useServicer } from "@/hooks/useServicer" // Add import
import { getInitials } from "@/utils"

function ContactSupportMenuItem() {
  const { hasSupport, handleContactSupport, isLoading } = useServicer("desktop")
  const { t } = useTranslation()

  if (isLoading || !hasSupport) return null

  return (
    <>
      <DropdownMenuSeparator />
      <DropdownMenuItem onClick={handleContactSupport}>
        <LifeBuoy className="mr-2 h-4 w-4" />
        <span>{t("user.contactSupport")}</span>
      </DropdownMenuItem>
    </>
  )
}

interface UserInfoProps {
  fullName?: string | null
  email?: string | null
  avatar?: string | null
  levelName?: string | null
  levelExpireTime?: number
}

function UserInfo({
  fullName,
  email,
  avatar,
  levelName,
  levelExpireTime,
}: UserInfoProps) {
  const { t } = useTranslation()
  const isMember = !!levelName
  const expireDate = levelExpireTime
    ? new Date(levelExpireTime * 1000).toLocaleDateString()
    : ""

  return (
    <div className="flex items-center gap-2.5 w-full min-w-0">
      <Avatar className="size-8">
        {avatar ? (
          <img
            src={avatar}
            alt={fullName || t("user.defaultName")}
            className="h-full w-full object-cover"
          />
        ) : (
          <AvatarFallback className="bg-zinc-600 text-white">
            {getInitials(fullName || t("user.defaultName"))}
          </AvatarFallback>
        )}
      </Avatar>
      <div className="flex flex-col items-start min-w-0">
        <p className="text-sm font-medium truncate w-full flex items-center gap-1">
          {fullName}
          {isMember && (
            <span className="text-[10px] bg-yellow-500/10 text-yellow-600 px-1.5 py-0.5 rounded border border-yellow-500/20 font-bold leading-none">
              {levelName}
            </span>
          )}
        </p>
        <p className="text-xs text-muted-foreground truncate w-full">{email}</p>
        {isMember && levelExpireTime && levelExpireTime > 0 && (
          <p className="text-[10px] text-muted-foreground/80 truncate w-full mt-0.5">
            {t("user.expireTime")}
            {expireDate}
          </p>
        )}
      </div>
    </div>
  )
}

export function User({ user }: { user: any }) {
  const { logout } = useAuth()
  const { isMobile, setOpenMobile } = useSidebar()
  const { t } = useTranslation()

  if (!user) {
    return (
      <SidebarMenu>
        <SidebarMenuItem>
          <SidebarMenuButton asChild>
            <RouterLink to="/login">
              <LogOut className="rotate-180" />{" "}
              {/* Reuse LogOut icon rotated or use LogIn if available */}
              <span>{t("user.login")}</span>
            </RouterLink>
          </SidebarMenuButton>
        </SidebarMenuItem>
      </SidebarMenu>
    )
  }

  const handleMenuClick = () => {
    if (isMobile) {
      setOpenMobile(false)
    }
  }
  const handleLogout = async () => {
    logout()
  }

  return (
    <SidebarMenu>
      <SidebarMenuItem>
        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <SidebarMenuButton
              size="lg"
              className="data-[state=open]:bg-sidebar-accent data-[state=open]:text-sidebar-accent-foreground"
              data-testid="user-menu"
            >
              <UserInfo
                fullName={user?.nickname || user?.full_name}
                email={user?.email}
                avatar={user?.headimg}
                levelName={user?.member_level_name}
                levelExpireTime={user?.level_expire_time}
              />
              <ChevronsUpDown className="ml-auto size-4 text-muted-foreground" />
            </SidebarMenuButton>
          </DropdownMenuTrigger>
          <DropdownMenuContent
            className="w-(--radix-dropdown-menu-trigger-width) min-w-56 rounded-lg"
            side={isMobile ? "bottom" : "right"}
            align="end"
            sideOffset={4}
          >
            <DropdownMenuLabel className="p-0 font-normal">
              <UserInfo
                fullName={user?.nickname || user?.full_name}
                email={user?.email}
                avatar={user?.headimg}
                levelName={user?.member_level_name}
                levelExpireTime={user?.level_expire_time}
              />
            </DropdownMenuLabel>
            <DropdownMenuSeparator />
            <DropdownMenuItem
              onClick={() =>
                window.open(
                  "https://mall.imagicbox.cn/h5/pages/member/index",
                  "_blank",
                )
              }
            >
              <Crown className="text-yellow-500" />
              <span>
                {user?.member_level_name
                  ? t("user.manageSubscription")
                  : t("user.upgradeToPro")}
              </span>
            </DropdownMenuItem>
            <DropdownMenuSeparator />
            <RouterLink to="/settings" onClick={handleMenuClick}>
              <DropdownMenuItem>
                <Settings />
                {t("user.settings")}
              </DropdownMenuItem>
            </RouterLink>
            <ContactSupportMenuItem />
            <DropdownMenuItem onClick={handleLogout}>
              <LogOut />
              {t("user.logout")}
            </DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>
      </SidebarMenuItem>
    </SidebarMenu>
  )
}
