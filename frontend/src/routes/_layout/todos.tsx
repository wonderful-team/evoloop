import { createFileRoute } from "@tanstack/react-router"
import { TodoList } from "@/components/Todos/TodoList"

export const Route = createFileRoute("/_layout/todos")({
    component: Todos,
})

function Todos() {
    return (
        <div className="h-full w-full">
            <TodoList />
        </div>
    )
}
