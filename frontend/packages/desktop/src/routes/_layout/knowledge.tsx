import { createFileRoute } from "@tanstack/react-router"
import { KnowledgeBasePage } from "@/components/KnowledgeBase/KnowledgeBasePage"

export const Route = createFileRoute("/_layout/knowledge")({
  component: KnowledgeRoute,
})

function KnowledgeRoute() {
  return <KnowledgeBasePage />
}
