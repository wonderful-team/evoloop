// 指令(Macro)列表 — 前端显示为"指令"，后端概念为 Macro
// 当前仅展示系统内置指令，隐藏新建/编辑/删除等编辑能力

import {createFileRoute, redirect} from "@tanstack/react-router"
import {MacroLibraryView} from "@/components/Learning/MacroLibraryView"
import {isLoggedIn} from "@/hooks/useAuth"

export const Route = createFileRoute("/_layout/projects/$projectId/macros")({
  component: ProjectMacrosRoute,
  beforeLoad: async () => {
    if (!isLoggedIn()) {
      throw redirect({ to: "/login" })
    }
  },
})

function ProjectMacrosRoute() {
  const { projectId } = Route.useParams()

  return (
    <div className="h-full w-full flex flex-col p-6">
      <MacroLibraryView projectId={parseInt(projectId, 10)} />
    </div>
  )
}
