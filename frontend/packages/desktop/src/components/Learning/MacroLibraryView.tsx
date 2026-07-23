// 指令(Macro)列表视图 — 前端显示为"指令"，后端概念为 Macro
// 当前仅展示系统内置指令，隐藏新建/编辑/删除/批量操作等编辑能力

import { Badge } from "@evoloop/shared/components/ui/badge"
import { Button } from "@evoloop/shared/components/ui/button"
import {
  Card,
  CardContent,
  CardFooter,
  CardHeader,
  CardTitle,
} from "@evoloop/shared/components/ui/card"
import { Checkbox } from "@evoloop/shared/components/ui/checkbox"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@evoloop/shared/components/ui/dialog"
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@evoloop/shared/components/ui/dropdown-menu"
import { Input } from "@evoloop/shared/components/ui/input"
import { Label } from "@evoloop/shared/components/ui/label"
import { ScrollArea } from "@evoloop/shared/components/ui/scroll-area"
import { Separator } from "@evoloop/shared/components/ui/separator"
import { Textarea } from "@evoloop/shared/components/ui/textarea"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { useNavigate } from "@tanstack/react-router"
import {
  CheckCheck,
  ChevronDown,
  ChevronRight,
  Edit,
  Eye,
  Loader2,
  MoreVertical,
  Play,
  Plus,
  RefreshCw,
  Save,
  Search,
  ShieldAlert,
  Trash2,
  Zap,
} from "lucide-react"
import { useMemo, useState } from "react"
import { useTranslation } from "react-i18next"
import { toast } from "sonner"
import { AtlasService, MacrosService } from "@/client/sdk.gen"
import type { MacroDetailDTO, MacroDTO } from "@/client/types.gen"
import { useProjectStore } from "@/stores/projectStore"
import { useChatStore } from "@/stores/chatStore"

interface MacroParam {
  name: string
  type?: string
  required?: boolean
  description?: string
}

interface MacroLibraryViewProps {
  projectId?: number
}

// ── component ────────────────────────────────────────────────────────────────
export function MacroLibraryView({ projectId }: MacroLibraryViewProps) {
  const { t } = useTranslation()
  const queryClient = useQueryClient()
  const navigate = useNavigate()
  const { projects } = useProjectStore()

  const [searchQuery, setSearchQuery] = useState("")
  const [selected, setSelected] = useState<Set<number>>(new Set())
  const [collapsed, setCollapsed] = useState<Set<string>>(new Set())
  const [macroToRun, setMacroToRun] = useState<MacroDTO | null>(null)
  const [runOpen, setRunOpen] = useState(false)
  const [runParams, setRunParams] = useState<Record<string, string>>({})
  const [detail, setDetail] = useState<MacroDetailDTO | null>(null)
  const [detailOpen, setDetailOpen] = useState(false)

  const getProjectName = (pId: number | null | undefined) => {
    if (pId == null) return "全局/未分配"
    const p = projects.find((proj) => proj.id === pId || proj.project_id === pId)
    return p ? p.name || p.project_name : `项目 #${pId}`
  }


  const [page, setPage] = useState(1)
  const pageSize = 50

  const { data: macros, isLoading } = useQuery({
    queryKey: ["macros", projectId ?? "all", page],
    queryFn: () =>
      MacrosService.listMacros({
        ...(projectId != null ? { projectId } : {}),
        skip: (page - 1) * pageSize,
        limit: pageSize,
      } as any) as unknown as Promise<MacroDTO[]>,
  })

  const invalidate = () =>
    queryClient.invalidateQueries({ queryKey: ["macros"] })

  const confirmMutation = useMutation({
    mutationFn: (ids: number[]) =>
      MacrosService.confirmBulk({ requestBody: { macro_ids: ids } }),
    onSuccess: (_r, ids) => {
      toast.success(t("learning.macros.confirmed", { count: ids.length }))
      setSelected(new Set())
      invalidate()
    },
    onError: (e: any) => toast.error(e.message),
  })

  const deleteMutation = useMutation({
    mutationFn: (id: number) => MacrosService.deleteMacro({ macroId: id }),
    onSuccess: () => {
      toast.success(t("learning.macros.deleted"))
      invalidate()
    },
    onError: (e: any) => toast.error(e.message),
  })



  const regenMutation = useMutation({
    mutationFn: (appMapId: number) => AtlasService.generateMacros({ appMapId }),
    onSuccess: () => {
      toast.success(t("learning.macros.regenStarted"))
      setTimeout(invalidate, 4000)
    },
    onError: (e: any) => toast.error(e.message),
  })

  const createMutation = useMutation({
    mutationFn: (projId: number | null) =>
      MacrosService.createMacro({
        requestBody: {
          name: t("learning.macros.newMacroName"),
          description: t("learning.macros.newMacroDesc"),
          project_id: projId,
          macro_script: "steps: []",
        },
      }),
    onSuccess: (newMacro) => {
      toast.success(t("learning.macros.createSuccess"))
      invalidate()
      navigate({
        to: "/learning/macros/$macroId/edit",
        params: { macroId: (newMacro as any).id.toString() },
      } as any)
    },
    onError: (e: any) => toast.error(e.message),
  })

  const bulkDeleteMutation = useMutation({
    mutationFn: async (ids: number[]) => {
      await Promise.all(ids.map((id) => MacrosService.deleteMacro({ macroId: id })))
      return ids
    },
    onSuccess: (_, ids) => {
      toast.success(t("learning.macros.bulkDeleteSuccess", { count: ids.length }))
      setSelected(new Set())
      invalidate()
    },
    onError: (e: any) => toast.error(e.message),
  })

  const runMutation = useMutation({
    mutationFn: ({
      id,
      params,
    }: {
      id: number
      params: Record<string, unknown>
    }) => {
      const threadId = useChatStore.getState().threadId
      return MacrosService.executeMacro({
        macroId: id,
        requestBody: {
          thread_id: threadId || undefined,
          params,
        },
      }) as unknown as Promise<{
        success: boolean
        message?: string
        extracted_data?: unknown
      }>
    },
    onSuccess: (r) => {
      if (r.success) {
        toast.success(r.message || t("learning.macros.runSuccess"))
      } else {
        toast.error(r.message || t("learning.macros.runFailed"))
      }
      setRunOpen(false)
      setMacroToRun(null)
    },
    onError: (e: any) => toast.error(e.message),
  })

  const filtered = useMemo(() => {
    const items = macros || []
    if (!searchQuery) return items
    const q = searchQuery.toLowerCase()
    return items.filter(
      (m) =>
        m.name.toLowerCase().includes(q) ||
        m.description.toLowerCase().includes(q) ||
        (m.entity || "").toLowerCase().includes(q),
    )
  }, [macros, searchQuery])

  const groups = useMemo(() => {
    const byEntity = new Map<string, MacroDTO[]>()
    for (const m of filtered) {
      const key = m.entity || t("learning.macros.noEntity")
      const list = byEntity.get(key) || []
      list.push(m)
      byEntity.set(key, list)
    }
    return [...byEntity.entries()].sort((a, b) => a[0].localeCompare(b[0]))
  }, [filtered, t])

  const pendingSelected = useMemo(
    () =>
      (macros || []).filter(
        (m) => selected.has(m.id) && m.status === "pending_review",
      ),
    [macros, selected],
  )

  const toggleSelect = (id: number) => {
    setSelected((prev) => {
      const next = new Set(prev)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })
  }

  const toggleGroupSelect = (items: MacroDTO[]) => {
    const pending = items.filter((m) => m.status === "pending_review")
    const allSelected = pending.every((m) => selected.has(m.id))
    setSelected((prev) => {
      const next = new Set(prev)
      for (const m of pending) {
        if (allSelected) next.delete(m.id)
        else next.add(m.id)
      }
      return next
    })
  }

  const toggleCollapse = (entity: string) => {
    setCollapsed((prev) => {
      const next = new Set(prev)
      if (next.has(entity)) next.delete(entity)
      else next.add(entity)
      return next
    })
  }

  const openDetail = async (m: MacroDTO) => {
    const d = (await MacrosService.getMacro({
      macroId: m.id,
    })) as unknown as MacroDetailDTO
    setDetail(d)
    setDetailOpen(true)
  }

  const openEdit = (m: MacroDTO) => {
    navigate({
      to: "/learning/macros/$macroId/edit",
      params: { macroId: m.id.toString() },
    } as any)
  }

  const openRun = (m: MacroDTO) => {
    setMacroToRun(m)
    setRunParams({})
    setRunOpen(true)
  }

  const handleRun = () => {
    if (!macroToRun) return
    const params: Record<string, unknown> = {}
    for (const p of (macroToRun.parameters || []) as MacroParam[]) {
      const raw = runParams[p.name]
      if (raw == null || raw === "") continue
      params[p.name] = p.type === "number" ? Number(raw) : raw
    }
    runMutation.mutate({ id: macroToRun.id, params })
  }

  const statusBadge = (status: string) => (
    <Badge
      variant="outline"
      className={`text-[10px] font-medium border px-1.5 py-0.5 ${
        status === "verified"
          ? "bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 border-emerald-500/20"
          : status === "pending_review"
          ? "bg-amber-500/10 text-amber-600 dark:text-amber-400 border-amber-500/20"
          : "bg-muted/50 text-muted-foreground border-border"
      }`}
    >
      {t(`learning.statusBadge.${status}`)}
    </Badge>
  )

  return (
    <div className="flex flex-col h-full space-y-4">
      {/* Toolbar */}
      <div className="flex items-center justify-between gap-4 bg-card p-4 rounded-xl border border-border shadow-sm">
        <div className="relative flex-1 max-w-md">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
          <Input
            placeholder={t("learning.macros.searchPlaceholder")}
            className="pl-10 h-9 text-sm"
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
          />
        </div>
        <div className="flex gap-2 items-center">
          {selected.size > 0 && (
            <>
              {/* 批量删除 — 暂时关闭，后续恢复可取消注释下方代码
              <Button
                variant="destructive"
                size="sm"
                className="h-9 text-sm gap-1.5 animate-in fade-in zoom-in-95 duration-200"
                disabled={bulkDeleteMutation.isPending}
                onClick={() => {
                  if (window.confirm(t("learning.macros.bulkDeleteConfirm", {count: selected.size}))) {
                    bulkDeleteMutation.mutate([...selected])
                  }
                }}
              >
                <Trash2 className="h-4 w-4" />
                {t("learning.macros.deleteSelected", {count: selected.size})
              </Button>
              */}
            </>
          )}
          {/* 批量确认 — 暂时关闭，后续恢复可取消注释下方代码
          <Button
            variant="default"
            size="sm"
            className="h-9 text-sm px-3 gap-1.5"
            disabled={pendingSelected.length === 0 || confirmMutation.isPending}
            onClick={() =>
              confirmMutation.mutate(pendingSelected.map((m) => m.id))
            }
          >
            <CheckCheck className="h-4 w-4" />
            {t("learning.macros.confirmSelected", {
              count: pendingSelected.length,
            })}
          </Button>
          */}
          {/* 新建指令按钮 — 暂时关闭，后续恢复可取消注释下方代码
          <Button
            variant="outline"
            size="sm"
            className="h-9 text-sm px-3 gap-1.5"
            disabled={createMutation.isPending}
            onClick={() => createMutation.mutate(projectId || null)}
          >
            <Plus className="h-4 w-4" />
            {t("learning.macros.createMacro")}
          </Button>
          */}
          <Badge variant="outline" className="px-3 py-1 font-bold h-9 flex items-center justify-center">
            第 {page} 页 (本页 {macros?.length || 0} 条)
          </Badge>

          <div className="flex items-center gap-1">
            <Button
              variant="outline"
              size="sm"
              className="h-9 text-sm px-3"
              disabled={page <= 1}
              onClick={() => setPage((p) => Math.max(1, p - 1))}
            >
              上一页
            </Button>
            <Button
              variant="outline"
              size="sm"
              className="h-9 text-sm px-3"
              disabled={!macros || macros.length < pageSize}
              onClick={() => setPage((p) => p + 1)}
            >
              下一页
            </Button>
          </div>
        </div>
      </div>

      {/* Grouped list */}
      <ScrollArea className="flex-1">
        {isLoading ? (
          <div className="grid grid-cols-1 gap-4 p-1">
            {[1, 2, 3].map((i) => (
              <Card
                key={i}
                className="animate-pulse bg-muted h-40 rounded-xl"
              />
            ))}
          </div>
        ) : groups.length === 0 ? (
          <div className="flex flex-col items-center justify-center py-20 bg-muted/10 rounded-2xl border-2 border-dashed">
            <Zap className="h-12 w-12 text-muted-foreground mb-4 opacity-20" />
            <p className="text-muted-foreground">
              {t("learning.macros.empty")}
            </p>
          </div>
        ) : (
          <div className="space-y-4 p-1">
            {groups.map(([entity, items]) => {
              const isCollapsed = collapsed.has(entity)
              const pendingCount = items.filter(
                (m) => m.status === "pending_review",
              ).length
              const allPendingSelected =
                pendingCount > 0 &&
                items
                  .filter((m) => m.status === "pending_review")
                  .every((m) => selected.has(m.id))
              const appMapId = items.find((m) => m.app_map_id)?.app_map_id
              return (
                <div key={entity} className="space-y-2">
                  {/* Group header */}
                  <div className="flex items-center gap-3 px-2">
                    <button
                      type="button"
                      className="flex items-center gap-1.5 text-sm font-semibold hover:text-primary transition-colors"
                      onClick={() => toggleCollapse(entity)}
                    >
                      {isCollapsed ? (
                        <ChevronRight className="h-4 w-4" />
                      ) : (
                        <ChevronDown className="h-4 w-4" />
                      )}
                      {entity}
                    </button>
                    <Badge variant="outline" className="text-[10px]">
                      {items.length}
                    </Badge>
                    {pendingCount > 0 && (
                      <Badge
                        variant="secondary"
                        className="text-[10px] bg-amber-500/10 text-amber-600 border-amber-500/20"
                      >
                        {t("learning.macros.pendingCount", {
                          count: pendingCount,
                        })}
                      </Badge>
                    )}
                    <div className="flex-1" />
                    {pendingCount > 0 && (
                      <span className="flex items-center gap-1.5 text-[11px] text-muted-foreground cursor-pointer">
                        <Checkbox
                          id={`select-pending-${entity}`}
                          checked={allPendingSelected}
                          onCheckedChange={() => toggleGroupSelect(items)}
                        />
                        <Label
                          htmlFor={`select-pending-${entity}`}
                          className="text-[11px] cursor-pointer"
                        >
                          {t("learning.macros.selectPending")}
                        </Label>
                      </span>
                    )}
                    {appMapId != null && (
                      <>
                        {/* 重新生成指令 — 暂时关闭，后续恢复可取消注释下方代码
                        <Button
                          variant="ghost"
                          size="sm"
                          className="h-7 text-[11px] gap-1"
                          disabled={regenMutation.isPending}
                          onClick={() => regenMutation.mutate(appMapId)}
                        >
                          <RefreshCw className="h-3 w-3" />
                          {t("learning.macros.regenerate")}
                        </Button>
                        */}
                      </>
                    )}
                  </div>

                  {!isCollapsed && (
                    <div className="grid grid-cols-1 gap-1">
                      {items.map((m) => (
                        <div
                          key={m.id}
                          className="group flex items-center gap-2 px-3 py-2 rounded-lg border border-border hover:border-primary/30 hover:bg-muted/20 transition-all"
                        >
                          <Checkbox
                            checked={selected.has(m.id)}
                            onCheckedChange={() => toggleSelect(m.id)}
                            className="shrink-0"
                          />
                          <div className="flex-1 min-w-0 space-y-0.5">
                            <div className="flex items-center gap-2">
                              <span className="text-sm font-medium truncate">
                                {m.name}
                              </span>
                              {statusBadge(m.status)}
                              {m.risk_tier && (
                                <span className="text-[10px] text-muted-foreground bg-muted px-1.5 py-0.5 rounded shrink-0">
                                  {m.risk_tier}
                                </span>
                              )}
                              {projectId == null && (
                                <span className="text-[10px] text-blue-600 bg-blue-500/10 px-1.5 py-0.5 rounded shrink-0">
                                  {getProjectName(m.project_id)}
                                </span>
                              )}
                              {m.requires_confirmation && (
                                <ShieldAlert className="h-3.5 w-3.5 text-amber-500 shrink-0" />
                              )}
                              <span className="text-[11px] text-muted-foreground truncate flex-1 min-w-0 hidden sm:inline">
                                {m.description}
                              </span>
                              <div className="flex items-center gap-1 shrink-0">
                                <Button
                                  size="sm"
                                  variant="secondary"
                                  className="h-6 text-xs px-2"
                                  disabled={!(m.is_active && m.status === "verified")}
                                  title={m.is_active && m.status === "verified" ? undefined : t("learning.macros.runNeedsConfirm")}
                                  onClick={() => openRun(m)}
                                >
                                  <Play className="h-2.5 w-2.5 fill-current mr-1" />
                                  {t("common.run")}
                                </Button>
                                <DropdownMenu>
                                  <DropdownMenuTrigger asChild>
                                    <Button variant="ghost" size="icon" className="h-6 w-6">
                                      <MoreVertical className="h-3.5 w-3.5" />
                                    </Button>
                                  </DropdownMenuTrigger>
                                  <DropdownMenuContent align="end">
                                    <DropdownMenuItem onClick={() => openDetail(m)}>
                                      <Eye className="mr-2 h-4 w-4" />
                                      {t("learning.viewDetails")}
                                    </DropdownMenuItem>
                                  </DropdownMenuContent>
                                </DropdownMenu>
                              </div>
                            </div>
                            {(Array.isArray(m.trigger_patterns) ? m.trigger_patterns : []).filter(Boolean).length > 0 && (
                              <div className="flex flex-wrap gap-1">
                                {(Array.isArray(m.trigger_patterns) ? m.trigger_patterns : [])
                                  .filter(Boolean)
                                  .map((p: string, i: number) => (
                                    <span key={i} className="text-[10px] bg-primary/5 text-primary px-1.5 py-0.5 rounded border border-primary/10 font-mono">
                                      {p}
                                    </span>
                                  ))}
                              </div>
                            )}
                          </div>
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              )
            })}
          </div>
        )}
      </ScrollArea>

      {/* Run dialog */}
      <Dialog open={runOpen} onOpenChange={setRunOpen}>
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle>
              {t("learning.macros.runTitle", { name: macroToRun?.name })}
            </DialogTitle>
            <DialogDescription>{macroToRun?.description}</DialogDescription>
          </DialogHeader>
          <div className="space-y-3 py-2">
            {((macroToRun?.parameters || []) as MacroParam[]).map((p) => (
              <div key={p.name} className="space-y-1.5">
                <Label htmlFor={`param-${p.name}`} className="text-xs">
                  {p.name}
                  {p.required && <span className="text-destructive"> *</span>}
                  <span className="text-muted-foreground ml-1.5">
                    {p.description}
                  </span>
                </Label>
                <Input
                  id={`param-${p.name}`}
                  type={p.type === "number" ? "number" : "text"}
                  value={runParams[p.name] || ""}
                  onChange={(e) =>
                    setRunParams((prev) => ({
                      ...prev,
                      [p.name]: e.target.value,
                    }))
                  }
                />
              </div>
            ))}
            {((macroToRun?.parameters || []) as MacroParam[]).length === 0 && (
              <p className="text-xs text-muted-foreground">
                {t("learning.macros.noParams")}
              </p>
            )}
          </div>
          <DialogFooter>
            <Button
              onClick={handleRun}
              disabled={runMutation.isPending}
              className="gap-1.5"
            >
              <Play className="h-3.5 w-3.5" />
              {t("common.run")}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Detail dialog */}
      <Dialog open={detailOpen} onOpenChange={setDetailOpen}>
        <DialogContent className="sm:max-w-2xl max-h-[80vh] overflow-hidden flex flex-col">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              {detail?.name}
              {detail && statusBadge(detail.status)}
            </DialogTitle>
            <DialogDescription>{detail?.description}</DialogDescription>
          </DialogHeader>
          <ScrollArea className="flex-1 min-h-0">
            <pre className="text-[11px] font-mono bg-muted/30 p-4 rounded-lg whitespace-pre-wrap break-all">
              {detail?.macro_script}
            </pre>
          </ScrollArea>
        </DialogContent>
      </Dialog>
    </div>
  )
}
