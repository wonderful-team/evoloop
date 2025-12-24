import { createRoute, createRootRoute } from "@tanstack/react-router"
import { Layout } from "./Layout"
import { IndexScreen } from "./screens/IndexScreen"
import { LoginScreen, loginLoader } from "./screens/LoginScreen"
import { DevicesScreen, devicesLoader } from "./screens/DevicesScreen"
import { ChatScreen } from "./screens/ChatScreen"
import { SearchScreen } from "./screens/SearchScreen"
import { redirect } from "@tanstack/react-router"

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

const indexRoute = createRoute({
    getParentRoute: () => layoutRoute,
    path: '/',
    component: IndexScreen,
    beforeLoad: () => {
        throw redirect({ to: '/devices' as any })
    }
})

const loginRoute = createRoute({
    getParentRoute: () => layoutRoute,
    path: '/login',
    component: LoginScreen,
    beforeLoad: loginLoader
})

const devicesRoute = createRoute({
    getParentRoute: () => layoutRoute,
    path: '/devices',
    component: DevicesScreen,
    beforeLoad: devicesLoader
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
        indexRoute,
        loginRoute,
        devicesRoute,
        chatRoute,
        searchRoute,
    ]),
])

export { routeTree }
