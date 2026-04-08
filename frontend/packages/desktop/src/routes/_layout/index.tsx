import { createFileRoute, Navigate, redirect } from "@tanstack/react-router"
import { isLoggedIn } from "@/hooks/useAuth"

export const Route = createFileRoute("/_layout/")({
  component: () => <Navigate to="/chat" />,
  beforeLoad: async () => {
    // 如果未登录，重定向到登录页
    if (!isLoggedIn()) {
      throw redirect({ to: "/login" })
    }
  },
})
