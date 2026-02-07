import { createFileRoute } from "@tanstack/react-router"
import { AndroidMirrorConsole } from "@/components/Learning/AndroidMirrorConsole"

export const Route = createFileRoute("/_layout/learning")({
    component: LearningPage,
})

function LearningPage() {
    return (
        <div className="space-y-8 animate-in fade-in slide-in-from-bottom-4 duration-700">
            <AndroidMirrorConsole />
        </div>
    )
}
