import { createFileRoute, redirect } from "@tanstack/react-router"
import { KnowledgeBasePage } from "@/components/KnowledgeBase/KnowledgeBasePage"
import { isLoggedIn } from "@/hooks/useAuth"

export const Route = createFileRoute("/_layout/knowledge")({
  component: KnowledgeRoute,
  beforeLoad: async () => {
    if (!isLoggedIn()) {
      throw redirect({ to: "/login" })
    }
  },
})

function KnowledgeRoute() {
  return <KnowledgeBasePage />
}
