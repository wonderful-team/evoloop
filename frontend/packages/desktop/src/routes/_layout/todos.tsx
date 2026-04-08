import { createFileRoute, redirect } from "@tanstack/react-router"
import { TodoList } from "@/components/Todos/TodoList"
import { isLoggedIn } from "@/hooks/useAuth"

export const Route = createFileRoute("/_layout/todos")({
    component: Todos,
    beforeLoad: async () => {
        if (!isLoggedIn()) {
            throw redirect({ to: "/login" })
        }
    },
})

function Todos() {
    return (
        <div className="h-full w-full">
            <TodoList />
        </div>
    )
}
