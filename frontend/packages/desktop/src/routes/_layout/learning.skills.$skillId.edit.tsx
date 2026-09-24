import {createFileRoute, redirect, useNavigate} from "@tanstack/react-router"
import {SkillEditorPage} from "@/components/Learning/SkillEditorPage"
import {isLoggedIn} from "@/hooks/useAuth"

export const Route = createFileRoute("/_layout/learning/skills/$skillId/edit")({
  component: SkillEditorRoute,
  beforeLoad: async () => {
    if (!isLoggedIn()) {
      throw redirect({ to: "/login" })
    }
  },
})

function SkillEditorRoute() {
  const { skillId } = Route.useParams()
  const navigate = useNavigate()

  return (
    <SkillEditorPage
      skillId={parseInt(skillId, 10)}
      onBack={() => navigate({ to: "/learning", search: { tab: "library" } })}
      onSave={() => navigate({ to: "/learning", search: { tab: "library" } })}
    />
  )
}
