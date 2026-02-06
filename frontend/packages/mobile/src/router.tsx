import { createRootRoute, createRoute } from "@tanstack/react-router"
import { useTranslation } from "react-i18next"
import { Button } from "@evoloop/shared/components/ui/button"
import { Layout } from "./Layout"
import { CloudChatScreen } from "./screens/CloudChatScreen"
import { DevicesScreen, devicesLoader } from "./screens/DevicesScreen"
import { ForgotPasswordScreen } from "./screens/ForgotPasswordScreen"
import { HelpScreen } from "./screens/HelpScreen"
import { IndexScreen } from "./screens/IndexScreen"
import { LocalChatScreen } from "./screens/LocalChatScreen"
import { LoginScreen, loginLoader } from "./screens/LoginScreen"
import { ProfileScreen } from "./screens/ProfileScreen"
import { ProjectsScreen } from "./screens/ProjectsScreen"
import { RegisterScreen } from "./screens/RegisterScreen"
import { SearchScreen } from "./screens/SearchScreen"
import { TabsLayout } from "./TabsLayout"

// 1. Create Route Hierarchy
const rootRoute = createRootRoute({
  notFoundComponent: () => {
    return <NotFound />
  },
})

function NotFound() {
  const { t } = useTranslation()
  return (
    <div className="p-4 bg-red-50 text-red-600 h-screen flex flex-col items-center justify-center space-y-4">
      <h1 className="text-xl font-bold"> {t("common.routeNotFound")} </h1>
      <Button variant="outline" onClick={() => window.location.href = "/"}>
        {t("common.back")}
      </Button>
    </div>
  )
}

const layoutRoute = createRoute({
  getParentRoute: () => rootRoute,
  id: "mobile-layout",
  component: Layout,
})

// Tab Routes Layout
const tabsRoute = createRoute({
  getParentRoute: () => layoutRoute,
  id: "tabs",
  component: TabsLayout,
})

const indexRoute = createRoute({
  getParentRoute: () => tabsRoute,
  path: "/",
  component: IndexScreen,
})

const devicesRoute = createRoute({
  getParentRoute: () => tabsRoute,
  path: "/devices",
  component: DevicesScreen,
  beforeLoad: devicesLoader,
})

const projectsRoute = createRoute({
  getParentRoute: () => tabsRoute,
  path: "/projects",
  component: ProjectsScreen,
  beforeLoad: devicesLoader, // Reuse login check
})

const profileRoute = createRoute({
  getParentRoute: () => tabsRoute,
  path: "/profile",
  component: ProfileScreen,
  beforeLoad: devicesLoader, // Reuse login check
})

// Full Screen Routes
const loginRoute = createRoute({
  getParentRoute: () => layoutRoute,
  path: "/login",
  component: LoginScreen,
  beforeLoad: loginLoader,
})

const localChatRoute = createRoute({
  getParentRoute: () => layoutRoute,
  path: "/chat/$deviceId",
  component: LocalChatScreen,
})

const cloudChatRoute = createRoute({
  getParentRoute: () => layoutRoute,
  path: "/cloud-chat/$conversationId",
  component: CloudChatScreen,
})

const helpRoute = createRoute({
  getParentRoute: () => layoutRoute,
  path: "/profile/help",
  component: HelpScreen,
})

const searchRoute = createRoute({
  getParentRoute: () => layoutRoute,
  path: "/search",
  component: SearchScreen,
})

const forgotPasswordRoute = createRoute({
  getParentRoute: () => layoutRoute,
  path: "/forgot-password",
  component: ForgotPasswordScreen,
})

const registerRoute = createRoute({
  getParentRoute: () => layoutRoute,
  path: "/register",
  component: RegisterScreen,
})

// 2. Build the Tree
const routeTree = rootRoute.addChildren([
  layoutRoute.addChildren([
    tabsRoute.addChildren([indexRoute, devicesRoute, projectsRoute, profileRoute]),
    loginRoute,
    localChatRoute,
    cloudChatRoute,
    searchRoute,
    forgotPasswordRoute,
    registerRoute,
    helpRoute,
  ]),
])

export { routeTree }
