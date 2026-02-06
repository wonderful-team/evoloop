import { Link, useLocation, useNavigate } from "@tanstack/react-router"
import { motion } from "framer-motion"
import { FolderOpen, Home, Menu, Monitor, Search, User } from "lucide-react"
import { useEffect, useRef } from "react"
import { useTranslation } from "react-i18next"
import { Button } from "@evoloop/shared/components/ui/button"
import { ConversationDrawer } from "./components/ConversationDrawer"
import { OnboardingOverlay } from "./components/OnboardingOverlay"
import { DevicesScreen } from "./screens/DevicesScreen"
import { HelpScreen } from "./screens/HelpScreen"
// Import Screens directly for pre-loading side-by-side
import { IndexScreen } from "./screens/IndexScreen"
import { ProfileScreen } from "./screens/ProfileScreen"
import { ProjectsScreen } from "./screens/ProjectsScreen"
import { useMobileStore } from "./stores/useMobileStore"

export function TabsLayout() {
  const { t } = useTranslation()
  const location = useLocation()
  const navigate = useNavigate()
  const path = location.pathname
  const { activeTab, setActiveTab } = useMobileStore()
  const isGuest = !localStorage.getItem("evoloop_token")
  const scrollContainerRef = useRef<HTMLDivElement>(null)

  const isActive = (p: string) => {
    if (p === "/" && path === "/") return true
    if (p !== "/" && path.startsWith(p)) return true
    return false
  }

  const showLocalTabs = activeTab === "local"

  // Sync State with URL & Scroll Position
  useEffect(() => {
    if (!scrollContainerRef.current) return

    if (path === "/" || path.startsWith("/profile")) {
      if (activeTab !== "cloud") {
        setActiveTab("cloud")
      }
      // Programmatically scroll to Cloud (0)
      scrollContainerRef.current.scrollTo({ left: 0, behavior: "smooth" })
    } else if (path.startsWith("/devices") || path.startsWith("/projects")) {
      if (activeTab !== "local") {
        setActiveTab("local")
      }
      // Programmatically scroll to Local (width)
      scrollContainerRef.current.scrollTo({
        left: window.innerWidth,
        behavior: "smooth",
      })
    }
  }, [path, activeTab, setActiveTab])

  const handleTabSwitch = (tab: "cloud" | "local") => {
    if (tab === activeTab) return
    if (tab === "cloud") {
      navigate({ to: "/" as any })
    } else {
      navigate({ to: "/devices" as any })
    }
  }

  // Using onMomentumScrollEnd logic equivalent for Web:
  // We can use a timeout debounce to detect scroll stop, then navigate.
  const scrollTimeoutRef = useRef<NodeJS.Timeout | undefined>(undefined)
  const onScroll = () => {
    if (!scrollContainerRef.current) return

    // Visual Tab update (instant)
    const scrollLeft = scrollContainerRef.current.scrollLeft
    const width = scrollContainerRef.current.clientWidth // Use clientWidth for accuracy

    if (scrollLeft < width / 2 && activeTab !== "cloud") {
      // setActiveTab('cloud') // Don't set yet, let Sync handle it?
      // Problem: UI needs to update instant.
    }

    clearTimeout(scrollTimeoutRef.current)
    scrollTimeoutRef.current = setTimeout(() => {
      // Scroll ended
      const finalScrollLeft = scrollContainerRef.current?.scrollLeft || 0

      if (finalScrollLeft < width / 2) {
        if (path.startsWith("/devices") || path.startsWith("/projects")) {
          navigate({ to: "/" as any })
        }
      } else {
        if (path === "/" || path.startsWith("/profile")) {
          navigate({ to: "/devices" as any })
        }
      }
    }, 150) // 150ms debounce for scroll end
  }

  // Manual Routing for Cloud Container
  const renderCloudContent = () => {
    if (path.startsWith("/profile/help")) return <HelpScreen />
    if (path.startsWith("/profile")) return <ProfileScreen />
    return <IndexScreen />
  }

  // Manual Routing for Local Container
  const renderLocalContent = () => {
    if (path.startsWith("/projects")) return <ProjectsScreen />
    return <DevicesScreen />
  }

  return (
    <div className="flex flex-col h-screen bg-background text-foreground relative overflow-hidden">
      <OnboardingOverlay />

      {/* Top Global Header with Safe Area Fix */}
      <div className="absolute top-0 left-0 right-0 z-30 pt-safe-top pt-2 flex flex-col pointer-events-none transition-all">
        <div className="px-4 h-[56px] flex items-center justify-between">
          {/* Left Slot: Fixed Width */}
          <div className="flex items-center w-[60px] pointer-events-auto">
            {!isGuest && activeTab === "cloud" && (
              <ConversationDrawer
                trigger={
                  <Button
                    variant="ghost"
                    size="icon"
                    className="-ml-2 h-10 w-10 rounded-full bg-background/60 backdrop-blur-md border border-border/50 shadow-sm transition-transform active:scale-95"
                  >
                    <Menu className="w-5.5 h-5.5 text-muted-foreground" />
                  </Button>
                }
              />
            )}
          </div>

          {/* Middle Slot: Switcher */}
          <div className="flex bg-muted/50 rounded-full p-1 relative backdrop-blur-md pointer-events-auto shadow-sm border border-border/50">
            <motion.div
              className="absolute top-1 bottom-1 bg-background shadow-sm rounded-full"
              initial={false}
              animate={{
                left: activeTab === "cloud" ? 4 : "50%",
                width: "calc(50% - 4px)",
              }}
              transition={{ type: "spring", stiffness: 400, damping: 30 }}
            />
            <button
              onClick={() => handleTabSwitch("cloud")}
              className={`relative z-10 px-6 py-1 text-sm font-medium transition-colors ${activeTab === "cloud" ? "text-primary" : "text-muted-foreground"}`}
            >
              {t("tabs.cloud")}
            </button>
            <button
              onClick={() => handleTabSwitch("local")}
              className={`relative z-10 px-6 py-1 text-sm font-medium transition-colors ${activeTab === "local" ? "text-primary" : "text-muted-foreground"}`}
            >
              {t("tabs.local")}
            </button>
          </div>

          {/* Right Slot: Fixed Width */}
          <div className="flex items-center justify-end w-[60px] pointer-events-auto">
            {activeTab === "local" && (
              <Button
                variant="ghost"
                size="icon"
                className="-mr-2 h-10 w-10 rounded-full bg-background/60 backdrop-blur-md border border-border/50 shadow-sm transition-transform active:scale-95"
                onClick={() => navigate({ to: "/search" as any })}
              >
                <Search className="w-5 h-5 text-muted-foreground" />
              </Button>
            )}
          </div>
        </div>
      </div>

      {/* Native Scroll Snap Container */}
      <div
        ref={scrollContainerRef}
        className="flex-1 flex overflow-x-auto snap-x snap-mandatory no-scrollbar"
        onScroll={onScroll}
      >
        {/* Cloud Context Container */}
        <div className="w-full min-w-full h-full pt-[calc(64px+env(safe-area-inset-top)+8px)] pb-[calc(56px+env(safe-area-inset-bottom))] overflow-y-auto no-scrollbar relative snap-center">
          {renderCloudContent()}
        </div>

        {/* Local Context Container */}
        <div className="w-full min-w-full h-full pt-[calc(64px+env(safe-area-inset-top)+8px)] pb-[calc(56px+env(safe-area-inset-bottom))] overflow-y-auto no-scrollbar relative snap-center">
          {renderLocalContent()}
        </div>
      </div>

      {/* Bottom Tab Bar */}
      <div className="border-t bg-background/80 backdrop-blur-md pb-safe absolute bottom-0 w-full z-40">
        <div className="flex justify-around items-center h-14 px-2">
          {/* Cloud Tabs */}
          <div
            className={`flex justify-around w-full ${showLocalTabs ? "hidden" : "flex"}`}
          >
            <Link
              to={"/" as any}
              className={`flex flex-col items-center gap-1 w-16 transition-colors ${isActive("/") ? "text-primary" : "text-muted-foreground"}`}
            >
              <Home className="w-5 h-5" />
              <span className="text-[10px] font-medium">{t("tabs.home")}</span>
            </Link>
            <Link
              to={"/profile" as any}
              className={`flex flex-col items-center gap-1 w-16 transition-colors ${isActive("/profile") ? "text-primary" : "text-muted-foreground"}`}
            >
              <User className="w-5 h-5" />
              <span className="text-[10px] font-medium">{t("tabs.me")}</span>
            </Link>
          </div>

          {/* Local Tabs */}
          <div
            className={`flex justify-around w-full ${!showLocalTabs ? "hidden" : "flex"}`}
          >
            <Link
              to={"/devices" as any}
              className={`flex flex-col items-center gap-1 w-16 transition-colors ${isActive("/devices") ? "text-primary" : "text-muted-foreground"}`}
            >
              <Monitor className="w-5 h-5" />
              <span className="text-[10px] font-medium">
                {t("tabs.devices")}
              </span>
            </Link>
            <Link
              to={"/projects" as any}
              className={`flex flex-col items-center gap-1 w-16 transition-colors ${isActive("/projects") ? "text-primary" : "text-muted-foreground"}`}
            >
              <FolderOpen className="w-5 h-5" />
              <span className="text-[10px] font-medium">
                {t("tabs.projects")}
              </span>
            </Link>
          </div>
        </div>
      </div>
    </div>
  )
}
