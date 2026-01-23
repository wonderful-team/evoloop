import { Outlet } from "@tanstack/react-router"

export function Layout() {
  return (
    <div className="min-h-screen bg-background text-foreground pb-safe">
      <Outlet />
    </div>
  )
}
