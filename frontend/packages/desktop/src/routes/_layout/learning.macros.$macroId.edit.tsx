import { createFileRoute, redirect, useNavigate } from "@tanstack/react-router"
import { MacroEditorPage } from "@/components/Learning/MacroEditorPage"
import { isLoggedIn } from "@/hooks/useAuth"

export const Route = createFileRoute("/_layout/learning/macros/$macroId/edit")({
  component: MacroEditorRoute,
  beforeLoad: async () => {
    if (!isLoggedIn()) {
      throw redirect({ to: "/login" })
    }
  },
})

function MacroEditorRoute() {
  const { macroId } = Route.useParams()
  const navigate = useNavigate()

  return (
    <MacroEditorPage
      macroId={parseInt(macroId, 10)}
      onBack={() => navigate({ to: "/learning", search: { tab: "macros" } })}
      onSave={() => navigate({ to: "/learning", search: { tab: "macros" } })}
    />
  )
}
