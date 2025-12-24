import { createRoute, createRootRoute } from "@tanstack/react-router"
import { Layout } from "./Layout"
import { TabsLayout } from "./TabsLayout"
import { IndexScreen } from "./screens/IndexScreen"
import { LoginScreen, loginLoader } from "./screens/LoginScreen"
import { DevicesScreen, devicesLoader } from "./screens/DevicesScreen"
import { ProjectsScreen } from "./screens/ProjectsScreen"
import { ProfileScreen } from "./screens/ProfileScreen"
import { ChatScreen } from "./screens/ChatScreen"
import { SearchScreen } from "./screens/SearchScreen"

// 1. Create Route Hierarchy
const rootRoute = createRootRoute({
    notFoundComponent: () => {
        return (
            <div className="p-4 bg-red-50 text-red-600" >
                <h1 className="text-xl font-bold" > Route Not Found </h1>
            </div>
        )
    }
})

const layoutRoute = createRoute({
    getParentRoute: () => rootRoute,
    id: 'mobile-layout',
    component: Layout,
})

// Tab Routes Layout
const tabsRoute = createRoute({
    getParentRoute: () => layoutRoute,
    id: 'tabs',
    component: TabsLayout,
})

const indexRoute = createRoute({
    getParentRoute: () => tabsRoute,
    path: '/',
    component: IndexScreen,
})

const devicesRoute = createRoute({
    getParentRoute: () => tabsRoute,
    path: '/devices',
    component: DevicesScreen,
    beforeLoad: devicesLoader
})

const projectsRoute = createRoute({
    getParentRoute: () => tabsRoute,
    path: '/projects',
    component: ProjectsScreen,
})

const profileRoute = createRoute({
    getParentRoute: () => tabsRoute,
    path: '/profile',
    component: ProfileScreen,
})

// Full Screen Routes
const loginRoute = createRoute({
    getParentRoute: () => layoutRoute,
    path: '/login',
    component: LoginScreen,
    beforeLoad: loginLoader
})

const chatRoute = createRoute({
    getParentRoute: () => layoutRoute,
    path: '/chat/$deviceId',
    component: ChatScreen,
})

const searchRoute = createRoute({
    getParentRoute: () => layoutRoute,
    path: '/search',
    component: SearchScreen,
})

// 2. Build the Tree
const routeTree = rootRoute.addChildren([
    layoutRoute.addChildren([
        tabsRoute.addChildren([
            indexRoute,
            devicesRoute,
            projectsRoute,
            profileRoute,
        ]),
        loginRoute,
        chatRoute,
        searchRoute,
    ]),
])

export { routeTree }
