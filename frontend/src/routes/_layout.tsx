import { createFileRoute, Outlet, useRouterState } from "@tanstack/react-router"

import { Footer } from "@/components/Common/Footer"
import AppSidebar from "@/components/Sidebar/AppSidebar"
import {
  SidebarInset,
  SidebarProvider,
  SidebarTrigger,
} from "@/components/ui/sidebar"

import { ProjectSwitcher } from "@/components/Sidebar/ProjectSwitcher"

export const Route = createFileRoute("/_layout")({
  component: Layout,
  // beforeLoad removed to allow Guest access
})

function Layout() {
  const router = useRouterState()
  const pathname = router.location.pathname
  const isFullWidth = pathname.includes('/chat') || pathname.includes('/files')

  return (
    <SidebarProvider>
      <AppSidebar />
      <SidebarInset>
        <header className="sticky top-0 z-10 flex h-16 shrink-0 items-center gap-2 border-b px-4 bg-background justify-between">
          <div className="flex items-center gap-2">
            <SidebarTrigger className="-ml-1 text-muted-foreground" />
          </div>
          <div className="absolute left-1/2 top-1/2 -translate-x-1/2 -translate-y-1/2">
            <ProjectSwitcher />
          </div>
          <div className="w-8" />
        </header>
        <main className={`flex-1 ${isFullWidth ? 'overflow-hidden' : 'p-6 md:p-8'}`}>
          <div className={isFullWidth ? 'h-full w-full' : 'mx-auto max-w-7xl'}>
            <Outlet />
          </div>
        </main>
        {!isFullWidth && <Footer />}
      </SidebarInset>
    </SidebarProvider>
  )
}

export default Layout
