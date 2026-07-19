import { createFileRoute, redirect } from "@tanstack/react-router"
import { Badge } from "@evoloop/shared/components/ui/badge"
import { ScrollArea } from "@evoloop/shared/components/ui/scroll-area"
import { Loader2, Map } from "lucide-react"
import { useEffect, useState } from "react"
import { MacroLibraryView } from "@/components/Learning/MacroLibraryView"
import { isLoggedIn } from "@/hooks/useAuth"

export const Route = createFileRoute("/_layout/projects/$projectId/macros")({
  component: ProjectMacrosRoute,
  beforeLoad: async () => {
    if (!isLoggedIn()) {
      throw redirect({ to: "/login" })
    }
  },
})

interface ModuleInfo {
  name: string
  entities: string[]
  entity_count: number
}

function ProjectMacrosRoute() {
  const { projectId } = Route.useParams()
  const pid = parseInt(projectId, 10)
  const [modules, setModules] = useState<ModuleInfo[]>([])
  const [loading, setLoading] = useState(true)
  const [selectedModule, setSelectedModule] = useState<string | null>(null)

  useEffect(() => {
    const fetchModules = async () => {
      try {
        const res = await fetch(`/api/v1/projects/${projectId}/modules`)
        if (res.ok) {
          const data = await res.json()
          setModules(data)
        }
      } catch { /* ignore */ }
      finally { setLoading(false) }
    }
    fetchModules()
  }, [projectId])

  return (
    <div className="h-full w-full flex p-6 gap-4">
      <div className="w-56 shrink-0 flex flex-col border rounded-lg bg-muted/5">
        <div className="flex items-center gap-2 px-3 h-10 border-b shrink-0">
          <Map className="h-4 w-4 text-muted-foreground" />
          <span className="text-xs font-medium text-muted-foreground">
            模块 ({modules.length})
          </span>
        </div>
        {loading ? (
          <div className="flex items-center justify-center py-8">
            <Loader2 className="h-4 w-4 animate-spin text-muted-foreground" />
          </div>
        ) : modules.length === 0 ? (
          <div className="p-3 text-xs text-muted-foreground text-center py-8">
            未生成模块数据
          </div>
        ) : (
          <ScrollArea className="flex-1">
            <div className="p-2 space-y-0.5">
              <button
                onClick={() => setSelectedModule(null)}
                className={`w-full text-left px-2 py-1.5 rounded text-xs transition-colors ${
                  !selectedModule ? "bg-primary/10 text-primary font-medium" : "text-muted-foreground hover:bg-muted"
                }`}
              >
                全部宏
              </button>
              {modules.map((m) => (
                <div key={m.name}>
                  <button
                    onClick={() => setSelectedModule(m.name)}
                    className={`w-full text-left px-2 py-1.5 rounded text-xs transition-colors flex items-center justify-between ${
                      selectedModule === m.name ? "bg-primary/10 text-primary font-medium" : "text-muted-foreground hover:bg-muted"
                    }`}
                  >
                    <span className="truncate">{m.name}</span>
                    <Badge variant="secondary" className="ml-1 text-[10px] px-1 py-0">
                      {m.entity_count}
                    </Badge>
                  </button>
                  {selectedModule === m.name && (
                    <div className="px-2 pb-1 flex flex-wrap gap-1">
                      {m.entities.map((e) => (
                        <span key={e} className="text-[10px] bg-secondary text-secondary-foreground px-1.5 py-0.5 rounded">
                          {e}
                        </span>
                      ))}
                    </div>
                  )}
                </div>
              ))}
            </div>
          </ScrollArea>
        )}
      </div>

      <div className="flex-1 min-w-0">
        <MacroLibraryView
          projectId={pid}
          key={selectedModule || "all"}
        />
      </div>
    </div>
  )
}
