import {createFileRoute, redirect} from "@tanstack/react-router"
import {ProjectList} from "@/components/Projects/ProjectList"
import {isLoggedIn} from "@/hooks/useAuth"

export const Route = createFileRoute("/_layout/projects/")({
  component: ProjectList,
  beforeLoad: async () => {
    if (!isLoggedIn()) {
      throw redirect({ to: "/login" })
    }
  },
})
