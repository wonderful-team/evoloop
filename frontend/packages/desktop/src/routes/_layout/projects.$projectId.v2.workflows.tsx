import { createFileRoute } from "@tanstack/react-router"
import { CheckSquare, Layers, Zap } from "lucide-react"
import { useState } from "react"
import { MacroLibraryView } from "@/components/Learning/MacroLibraryView"
import { TaskList } from "@/components/Projects/Modules/Tasks/TaskList"

export const Route = createFileRoute("/_layout/projects/$projectId/v2/workflows")({
  component: WorkflowsPage,
})

function WorkflowsPage() {
  const [activeSubView, setActiveSubView] = useState<"macros" | "tasks">("macros")

  return (
    <div className="flex flex-col h-full w-full overflow-hidden">
      <div className="flex-1 overflow-auto p-6 space-y-6 max-w-7xl mx-auto w-full">
        <div className="flex justify-between items-center">
          <div className="flex items-center gap-3">
            <div className="p-2.5 bg-primary/10 rounded-xl text-primary shrink-0">
              <Layers className="h-6 w-6" />
            </div>
            <div>
              <h2 className="text-2xl font-bold tracking-tight">任务与流程中枢</h2>
              <p className="text-sm text-muted-foreground mt-0.5">
                管理 Macro SOP 自动化流程与 Agent 创生的任务看板
              </p>
            </div>
          </div>

          <div className="flex items-center gap-1 bg-muted/40 p-1 rounded-lg border border-border">
            <button
              onClick={() => setActiveSubView("macros")}
              className={`flex items-center gap-2 px-3.5 py-1.5 text-xs font-medium rounded-md transition-all ${
                activeSubView === "macros"
                  ? "bg-background text-foreground shadow-xs"
                  : "text-muted-foreground hover:text-foreground"
              }`}
            >
              <Zap className="h-3.5 w-3.5 text-amber-500" />
              <span>Macro SOP 自动化库</span>
            </button>

            <button
              onClick={() => setActiveSubView("tasks")}
              className={`flex items-center gap-2 px-3.5 py-1.5 text-xs font-medium rounded-md transition-all ${
                activeSubView === "tasks"
                  ? "bg-background text-foreground shadow-xs"
                  : "text-muted-foreground hover:text-foreground"
              }`}
            >
              <CheckSquare className="h-3.5 w-3.5 text-blue-500" />
              <span>任务看板与拆解</span>
            </button>
          </div>
        </div>

        <div className="w-full">
          {activeSubView === "macros" && <MacroLibraryView />}
          {activeSubView === "tasks" && <TaskList />}
        </div>
      </div>
    </div>
  )
}
