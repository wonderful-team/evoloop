import { useEffect, useState } from "react"
import { useTranslation } from "react-i18next"
import { Loader2, AlertCircle, Map, Route, Table2, ListChecks, Eye } from "lucide-react"
import { Card, CardContent, CardHeader, CardTitle } from "@evoloop/shared/components/ui/card"
import { Button } from "@evoloop/shared/components/ui/button"
import { AtlasService } from "@/client"

interface AppMapItem {
  id: number
  entity: string
  platform: string
  status: string
  map_version: number
  actions_count: number
  macro_count: number
  pending_count: number
}

export function AppMapPanel({ projectId }: { projectId: string }) {
  const { t } = useTranslation()
  const [maps, setMaps] = useState<AppMapItem[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    const load = async () => {
      setLoading(true)
      setError(null)
      try {
        const data = await AtlasService.listAppMaps({ projectId: Number(projectId) })
        const items = Array.isArray(data) ? (data as AppMapItem[]) : []
        items.sort((a, b) => a.entity.localeCompare(b.entity))
        setMaps(items)
      } catch (err) {
        setError(err instanceof Error ? err.message : "Failed to load AppMaps")
      } finally {
        setLoading(false)
      }
    }
    load()
  }, [projectId])

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
      </div>
    )
  }

  if (error) {
    return (
      <Card className="border-destructive">
        <CardContent className="flex items-center gap-3 pt-6">
          <AlertCircle className="h-5 w-5 text-destructive" />
          <p className="text-destructive text-sm">{error}</p>
        </CardContent>
      </Card>
    )
  }

  if (maps.length === 0) {
    return (
      <Card>
        <CardContent className="flex flex-col items-center gap-4 pt-12 pb-12 text-muted-foreground">
          <Map className="h-12 w-12" />
          <p className="text-lg font-medium">{t("generation.appmap.empty_title", "还没有生成 AppMap")}</p>
          <p className="text-sm">{t("generation.appmap.empty_desc", "请先在「生成物管理」面板中触发 AppMap 生成")}</p>
          <Button variant="outline" onClick={() => window.history.back()}>
            {t("generation.back", "返回")}
          </Button>
        </CardContent>
      </Card>
    )
  }

  const stats = {
    total: maps.length,
    draft: maps.filter((m) => m.status === "active").length,
    actions: maps.reduce((s, m) => s + m.actions_count, 0),
    macros: maps.reduce((s, m) => s + m.macro_count, 0),
    pending: maps.filter((m) => m.pending_count > 0).length,
  }

  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-2xl font-bold tracking-tight">
          {t("generation.appmap.title", "应用地图 (AppMap)")}
        </h2>
        <p className="text-muted-foreground">
          {t("generation.appmap.subtitle", "共 {count} 个实体，{actions} 个操作，{macros} 个宏", {
            count: stats.total,
            actions: stats.actions,
            macros: stats.macros,
          })}
        </p>
      </div>

      <div className="grid grid-cols-4 gap-4">
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium text-muted-foreground">
              {t("generation.appmap.entities", "实体")}
            </CardTitle>
          </CardHeader>
          <CardContent>
            <p className="text-3xl font-bold">{stats.total}</p>
          </CardContent>
        </Card>
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium text-muted-foreground">
              {t("generation.appmap.actions", "操作")}
            </CardTitle>
          </CardHeader>
          <CardContent>
            <p className="text-3xl font-bold">{stats.actions}</p>
          </CardContent>
        </Card>
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium text-muted-foreground">
              {t("generation.appmap.macros", "宏")}
            </CardTitle>
          </CardHeader>
          <CardContent>
            <p className="text-3xl font-bold">{stats.macros}</p>
          </CardContent>
        </Card>
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium text-muted-foreground">
              {t("generation.appmap.pending", "待审核")}
            </CardTitle>
          </CardHeader>
          <CardContent>
            <p className="text-3xl font-bold">{stats.pending}</p>
          </CardContent>
        </Card>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>{t("generation.appmap.entity_list", "实体列表")}</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="divide-y">
            {maps.map((m) => (
              <div key={m.id} className="flex items-center justify-between py-3">
                <div className="flex items-center gap-3">
                  <Map className="h-5 w-5 text-muted-foreground shrink-0" />
                  <div>
                    <p className="font-medium">{m.entity}</p>
                    <div className="flex items-center gap-3 text-xs text-muted-foreground">
                      <span className="flex items-center gap-1">
                        <ListChecks className="h-3 w-3" />
                        {m.actions_count} actions
                      </span>
                      <span className="flex items-center gap-1">
                        <Table2 className="h-3 w-3" />
                        v{m.map_version}
                      </span>
                    </div>
                  </div>
                </div>
                <div className="flex items-center gap-2">
                  {m.pending_count > 0 && (
                    <span className="text-xs bg-yellow-100 text-yellow-800 px-2 py-1 rounded">
                      {m.pending_count} pending
                    </span>
                  )}
                  <span
                    className={`text-xs px-2 py-1 rounded ${
                      m.status === "active"
                        ? "bg-green-100 text-green-800"
                        : m.status === "draft"
                          ? "bg-gray-100 text-gray-800"
                          : "bg-red-100 text-red-800"
                    }`}
                  >
                    {m.status}
                  </span>
                </div>
              </div>
            ))}
          </div>
        </CardContent>
      </Card>
    </div>
  )
}
