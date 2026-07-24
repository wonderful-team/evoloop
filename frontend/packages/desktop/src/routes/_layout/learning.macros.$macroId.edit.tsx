// 指令(Macro)编辑器 — 暂时关闭编辑功能
// 后续恢复：删除第 8-12 行的 redirect beforeLoad 即可恢复编辑页面

import { createFileRoute, redirect, useNavigate } from "@tanstack/react-router"
import { MacroEditorPage } from "@/components/Learning/MacroEditorPage"

export const Route = createFileRoute("/_layout/learning/macros/$macroId/edit")({
  // 编辑功能暂时关闭，重定向到学习中心
  beforeLoad: async () => {
    throw redirect({ to: "/learning" })
  },
  // 后续恢复编辑：删除上面 beforeLoad，取消注释下面两行
  // component: MacroEditorRoute,
  // beforeLoad: async () => {
  //   if (!isLoggedIn()) {
  //     throw redirect({ to: "/login" })
  //   }
  // },
})

function _MacroEditorRoute() {
  const { macroId } = Route.useParams()
  const navigate = useNavigate()

  return (
    <MacroEditorPage
      macroId={Number(macroId)}
      onBack={() => navigate({ to: "/learning" })}
      onSave={() => navigate({ to: "/learning?tab=macros" })}
    />
  )
}
