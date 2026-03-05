import { createFileRoute, useNavigate } from "@tanstack/react-router"
import { SkillEditorPage } from "@/components/Learning/SkillEditorPage"

export const Route = createFileRoute("/_layout/learning/skills/$skillId/edit")({
    component: SkillEditorRoute,
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
