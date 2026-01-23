import { useNavigate } from "@tanstack/react-router"
import {
  BookOpen,
  CreditCard,
  Crown,
  Globe,
  LifeBuoy,
  LogOut,
  User,
} from "lucide-react"
import { useTranslation } from "react-i18next"
import { Button } from "@evoloop/shared/components/ui/button"
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@evoloop/shared/components/ui/dropdown-menu"
import useAuth from "../hooks/useAuth"
import { useMemberCancellation } from "../hooks/useMemberCancellation"
import { useServicer } from "../hooks/useServicer"

function ProfileSupportButton() {
  const { t } = useTranslation()
  const { hasSupport, handleContactSupport, isLoading } = useServicer("mobile")

  if (isLoading || !hasSupport) return null

  return (
    <Button
      variant="outline"
      className="w-full gap-2 mb-4"
      onClick={handleContactSupport}
    >
      <LifeBuoy className="w-4 h-4" />
      {t("profile.contactSupport")}
    </Button>
  )
}

function ProfileCancellation() {
  const { t } = useTranslation()
  const { info, apply, cancel, isApplying, isCanceling } =
    useMemberCancellation("mobile")

  // Status: 1=audit, 2=success, 3=refuse, -1=cancel/none?
  // Need to verify exact status codes from MemberCancel model.
  // Assuming logic: if info exists and status is "audit" (often 0 or 1), show Cancel Apply.
  // Based on Membercancel.php logic, it returns info.
  // Let's assume typical: status 0/1 = pending.

  const isPending = (info as any)?.status === 0 || (info as any)?.status === 1

  const handleApply = () => {
    if (window.confirm(t("profile.confirmDelete"))) {
      apply()
    }
  }

  const handleCancel = () => {
    if (window.confirm(t("profile.confirmWithdraw"))) {
      cancel()
    }
  }

  if (isPending) {
    return (
      <Button
        variant="outline"
        className="w-full gap-2 mb-4 border-red-200 text-red-600 hover:text-red-700 hover:bg-red-50"
        disabled={isCanceling}
        onClick={handleCancel}
      >
        {isCanceling ? t("profile.processing") : t("profile.withdrawDeletion")}
      </Button>
    )
  }

  return (
    <Button
      variant="ghost"
      className="w-full gap-2 mb-4 text-muted-foreground hover:text-red-600 hover:bg-red-50"
      disabled={isApplying}
      onClick={handleApply}
    >
      {t("profile.deleteAccount")}
    </Button>
  )
}

function ProfileLanguageSwitcher() {
  const { t, i18n } = useTranslation()

  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button variant="outline" className="w-full gap-2 mb-4 justify-start">
          <Globe className="w-4 h-4 ml-0.5" />
          <span className="flex-1 text-left">{t("profile.language")}</span>
          <span className="text-xs text-muted-foreground mr-1">
            {i18n.language === "zh"
              ? t("profile.chinese")
              : t("profile.english")}
          </span>
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" className="w-[200px]">
        <DropdownMenuItem onClick={() => i18n.changeLanguage("en")}>
          {t("profile.english")}
        </DropdownMenuItem>
        <DropdownMenuItem onClick={() => i18n.changeLanguage("zh")}>
          {t("profile.chinese")}
        </DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  )
}

export function ProfileScreen() {
  const { t } = useTranslation()
  const navigate = useNavigate()
  const { user, logout } = useAuth()
  const token = localStorage.getItem("evoloop_token")

  const handleLogout = async () => {
    await logout()
    navigate({ to: "/" as any })
  }

  // Guest View
  if (!token) {
    return (
      <div className="p-4 flex flex-col min-h-full bg-background animate-in fade-in duration-500">
        <h1 className="text-xl font-bold mb-6">{t("profile.title")}</h1>

        <div className="flex flex-col gap-6 flex-1 items-center justify-center text-center">
          <div className="w-24 h-24 bg-muted rounded-full flex items-center justify-center mb-4">
            <User className="w-12 h-12 text-muted-foreground" />
          </div>
          <div className="max-w-xs space-y-2">
            <h2 className="text-xl font-semibold">
              {t("profile.guestTitle")}
            </h2>
            <p className="text-sm text-muted-foreground">
              {t("profile.guestDesc")}
            </p>
          </div>
          <div className="grid gap-3 w-full max-w-xs mt-4">
            <Button onClick={() => navigate({ to: "/login" as any })}>
              {t("auth.login.submit")}
            </Button>
            <Button
              variant="outline"
              onClick={() => navigate({ to: "/register" as any })}
            >
              {t("auth.login.signUp")}
            </Button>
          </div>
        </div>

        <ProfileLanguageSwitcher />

        <Button
          variant="outline"
          className="w-full gap-2 mt-4"
          onClick={() => navigate({ to: "/profile/help" as any })}
        >
          <BookOpen className="w-4 h-4" />
          {t("profile.manual")}
        </Button>
      </div>
    )
  }

  const isMember = !!user?.member_level_name
  const expireDate = user?.level_expire_time
    ? new Date(user.level_expire_time * 1000).toLocaleDateString()
    : ""

  return (
    <div className="p-4 flex flex-col min-h-full bg-background">
      <h1 className="text-xl font-bold mb-6">{t("profile.title")}</h1>

      <div className="flex flex-col gap-6 flex-1">
        {/* User Info Header */}
        <div className="flex items-center gap-4">
          <div className="w-16 h-16 bg-muted rounded-full overflow-hidden flex items-center justify-center border-2 border-border">
            {user?.headimg ? (
              <img
                src={user.headimg}
                alt="Avatar"
                className="w-full h-full object-cover"
              />
            ) : (
              <User className="w-8 h-8 text-muted-foreground" />
            )}
          </div>
          <div>
            <h2 className="text-lg font-semibold">
              {user?.nickname || "User"}
            </h2>
            <p className="text-sm text-muted-foreground">{user?.email}</p>
          </div>
        </div>

        {/* Membership Card */}
        <div
          className={`rounded-xl p-5 text-white relative overflow-hidden shadow-lg transition-all ${isMember ? "bg-gradient-to-br from-yellow-600 to-yellow-800" : "bg-gradient-to-br from-zinc-700 to-zinc-900"}`}
        >
          {/* Background Decorative Circles */}
          <div className="absolute -top-10 -right-10 w-32 h-32 bg-white/10 rounded-full blur-2xl" />
          <div className="absolute bottom-0 left-0 w-24 h-24 bg-black/10 rounded-full blur-xl" />

          <div className="relative z-10">
            <div className="flex justify-between items-start mb-4">
              <div>
                <p className="text-xs opacity-80 uppercase tracking-wider mb-1">
                  {t("profile.currentPlan")}
                </p>
                <h3 className="text-2xl font-bold flex items-center gap-2">
                  {isMember ? (
                    <Crown className="w-5 h-5 text-yellow-300" />
                  ) : (
                    <CreditCard className="w-5 h-5 text-zinc-300" />
                  )}
                  {user?.member_level_name || t("profile.freePlan")}
                </h3>
              </div>
              {isMember && (
                <div className="bg-white/20 backdrop-blur-sm px-2 py-1 rounded text-xs font-medium border border-white/10">
                  {t("profile.pro")}
                </div>
              )}
            </div>

            <div className="space-y-1">
              {isMember ? (
                <>
                  <p className="text-sm opacity-90">
                    {t("profile.validUntil")} {expireDate}
                  </p>
                  <p className="text-xs opacity-75">
                    {t("profile.autoRenewalOff")}
                  </p>
                </>
              ) : (
                <p className="text-sm opacity-90">{t("profile.upgradeHint")}</p>
              )}
            </div>

            <div className="mt-4 pt-4 border-t border-white/10 flex justify-end">
              <Button
                variant="secondary"
                size="sm"
                className="h-8 bg-white/90 text-black hover:bg-white border-0 shadow-none font-medium"
                onClick={() =>
                  window.open(
                    "https://mall.imagicbox.cn/h5/pages/member/index",
                    "_blank",
                  )
                }
              >
                {isMember
                  ? t("profile.manageSubscription")
                  : t("profile.upgradeNow")}
              </Button>
            </div>
          </div>
        </div>

        {/* Stats Row (Optional, if we have data) */}
        <div className="grid grid-cols-2 gap-4">
          <div className="bg-muted/50 p-4 rounded-lg">
            <p className="text-xs text-muted-foreground">
              {t("profile.balance")}
            </p>
            <p className="text-xl font-bold">¥{user?.balance || "0.00"}</p>
          </div>
          <div className="bg-muted/50 p-4 rounded-lg">
            <p className="text-xs text-muted-foreground">
              {t("profile.points")}
            </p>
            <p className="text-xl font-bold">{user?.point || 0}</p>
          </div>
        </div>
      </div>

      <ProfileLanguageSwitcher />

      <Button
        variant="outline"
        className="w-full gap-2 mb-4"
        onClick={() => navigate({ to: "/profile/help" as any })}
      >
        <BookOpen className="w-4 h-4" />
        {t("profile.manual")}
      </Button>

      <ProfileSupportButton />
      <ProfileCancellation />

      <Button
        variant="destructive"
        className="w-full gap-2"
        onClick={handleLogout}
      >
        <LogOut className="w-4 h-4" />
        {t("profile.logout")}
      </Button>
    </div>
  )
}
