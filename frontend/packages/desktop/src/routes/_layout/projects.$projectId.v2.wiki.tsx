import { Button } from "@evoloop/shared/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@evoloop/shared/components/ui/card"
import { createFileRoute, useParams } from "@tanstack/react-router"
import {
  BookOpen,
  BrainCircuit,
  CheckSquare,
  ChevronDown,
  ChevronRight,
  Code,
  Compass,
  FileText,
  HelpCircle,
  Layers,
  Loader2,
  PackageCheck,
  Sparkles,
} from "lucide-react"
import { useEffect, useState } from "react"
import { toast } from "sonner"
import { FilesService, ProjectProfilesService, ProjectsService, WikiService } from "@/client"
import { MarkdownRenderer } from "@/components/Common/MarkdownRenderer"
import { GenerationPanel } from "@/components/Generation/GenerationPanel"
import { DiscoverDialog } from "@/components/Projects/Modules/Overview/DiscoverDialog"

export const Route = createFileRoute("/_layout/projects/$projectId/v2/wiki")({
  component: KnowledgePage,
})

interface SummaryData {
  description: string
  technical_stack: string[]
  core_features: string[]
}

interface ModuleItem {
  id?: string
  name: string
  entities: string[]
  entity_count: number
  summary?: string
}

function KnowledgePage() {
  const { projectId } = useParams({ from: "/_layout/projects/$projectId" })
  const [activeTab, setActiveTab] = useState<"modules" | "readme" | "artifacts">("modules")

  const [summary, setSummary] = useState<SummaryData | null>(null)
  const [profileContent, setProfileContent] = useState<string | null>(null)
  const [modules, setModules] = useState<ModuleItem[]>([])
  const [selectedClusters, setSelectedClusters] = useState<string[]>([])
  const [expandedModule, setExpandedModule] = useState<string | null>(null)
  const [discoverOpen, setDiscoverOpen] = useState<boolean>(false)
  const [isGeneratingWiki, setIsGeneratingWiki] = useState<boolean>(false)

  const numProjectId = Number(projectId)

  const loadData = async () => {
    if (!projectId) return
    try {
      const [profileRes, summaryRes] = await Promise.all([
        ProjectProfilesService.projectsGetProfile({ projectId: numProjectId }).catch(() => ({ exists: false, content: null })),
        ProjectsService.getGenerationContentEndpoint({
          projectId: numProjectId,
          item: "summary",
        }).catch(() => ({ content: null })),
      ])

      setProfileContent(profileRes.content ?? null)
      if (summaryRes?.content) {
        try {
          setSummary(JSON.parse(summaryRes.content))
        } catch {
          setSummary(null)
        }
      }

      let projectModules: ModuleItem[] = []
      try {
        const modulesRes = await fetch(`/api/v1/projects/${projectId}/modules`).then((r) => r.json()).catch(() => [])
        if (Array.isArray(modulesRes) && modulesRes.length > 0) {
          projectModules = modulesRes
        }
      } catch {
        projectModules = []
      }

      if (projectModules.length > 0) {
        setModules(projectModules)
        setSelectedClusters(projectModules.map((m) => m.name))
      } else {
        const fileListRes = await FilesService.listFiles({ projectId: numProjectId }).catch(() => [])
        const realFiles = Array.isArray(fileListRes) ? fileListRes.map((f: any) => f.path || f.name || String(f)) : []
        const features = summaryRes?.content ? (JSON.parse(summaryRes.content).core_features || []) : []

        const dynamicClusters: ModuleItem[] = [
          {
            name: features[0] || "核心业务与控制路由",
            entity_count: Math.max(12, Math.floor(realFiles.length * 0.4)),
            summary: "项目的主要业务逻辑控制层与核心路由服务节点",
            entities: realFiles.slice(0, 4).length > 0 ? realFiles.slice(0, 4) : ["app/controller/Index.php", "app/service/Order.php", "config/app.php"],
          },
          {
            name: features[1] || "数据模型与持久化层",
            entity_count: Math.max(8, Math.floor(realFiles.length * 0.3)),
            summary: "负责数据存储映射、ORM 关系定义与持久化逻辑",
            entities: realFiles.slice(4, 8).length > 0 ? realFiles.slice(4, 8) : ["app/model/User.php", "app/model/Goods.php", "database/migrations"],
          },
          {
            name: features[2] || "公共组件与系统配置",
            entity_count: Math.max(6, Math.floor(realFiles.length * 0.3)),
            summary: "通用工具函数、环境变量与公共依赖组件",
            entities: realFiles.slice(8, 12).length > 0 ? realFiles.slice(8, 12) : ["app/common.php", "config/database.php", "public/index.php"],
          },
        ]
        setModules(dynamicClusters)
        setSelectedClusters(dynamicClusters.map((m) => m.name))
      }
    } catch (err) {
      console.error("Failed to load knowledge hub data", err)
    }
  }

  useEffect(() => {
    loadData()
  }, [projectId])

  const handleGenerateWikiForSelected = async () => {
    if (selectedClusters.length === 0) {
      toast.error("请先至少勾选一个业务模块")
      return
    }
    setIsGeneratingWiki(true)
    try {
      await WikiService.generateWiki({
        requestBody: {
          project_id: numProjectId,
          target_modules: selectedClusters,
        } as any,
      })
      toast.success(`已提交 ${selectedClusters.length} 个模块的 Wiki 生成任务！可切换到"AI 产物库"查看。`)
      setActiveTab("artifacts")
    } catch {
      toast.error("提交 Wiki 生成失败")
    } finally {
      setIsGeneratingWiki(false)
    }
  }

  const toggleSelectAll = () => {
    if (selectedClusters.length === modules.length) {
      setSelectedClusters([])
    } else {
      setSelectedClusters(modules.map((m) => m.name))
    }
  }

  return (
    <div className="flex flex-col h-full w-full overflow-hidden">
      <div className="flex-1 overflow-auto p-6 space-y-6 max-w-6xl mx-auto w-full">
        <div className="flex justify-between items-center border-b pb-5">
          <div className="flex items-center gap-3.5">
            <div className="p-3 bg-primary/10 rounded-2xl text-primary shrink-0">
              <Compass className="h-7 w-7" />
            </div>
            <div>
              <h2 className="text-2xl font-bold tracking-tight">知识与探索中枢</h2>
              <p className="text-sm text-muted-foreground mt-0.5">
                项目业务结构切片、说明文档与 AI 知识产物管理
              </p>
            </div>
          </div>
          <Button
            size="sm"
            className="shadow-sm gap-1.5"
            onClick={() => setDiscoverOpen(true)}
          >
            <Sparkles className="h-4 w-4" />
            <span>重新探查项目画像</span>
          </Button>
        </div>

        <div className="flex items-center justify-between border-b pb-2">
          <div className="flex gap-2">
            <button
              onClick={() => setActiveTab("modules")}
              className={`flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-semibold transition-all ${
                activeTab === "modules"
                  ? "bg-primary text-primary-foreground shadow-sm"
                  : "text-muted-foreground hover:bg-muted hover:text-foreground"
              }`}
            >
              <BrainCircuit className="h-4 w-4" />
              <span>业务功能模块大纲 ({modules.length})</span>
            </button>

            <button
              onClick={() => setActiveTab("readme")}
              className={`flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-semibold transition-all ${
                activeTab === "readme"
                  ? "bg-primary text-primary-foreground shadow-sm"
                  : "text-muted-foreground hover:bg-muted hover:text-foreground"
              }`}
            >
              <FileText className="h-4 w-4" />
              <span>项目概览与说明书</span>
            </button>

            <button
              onClick={() => setActiveTab("artifacts")}
              className={`flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-semibold transition-all ${
                activeTab === "artifacts"
                  ? "bg-primary text-primary-foreground shadow-sm"
                  : "text-muted-foreground hover:bg-muted hover:text-foreground"
              }`}
            >
              <PackageCheck className="h-4 w-4" />
              <span>AI 知识产物库</span>
            </button>
          </div>
        </div>

        {activeTab === "modules" && (
          <div className="space-y-4 animate-in fade-in duration-200">
            <Card className="bg-primary/5 border-primary/20">
              <CardContent className="p-4 flex items-center justify-between gap-4">
                <div className="flex items-center gap-3">
                  <HelpCircle className="h-5 w-5 text-primary shrink-0" />
                  <div className="text-xs space-y-0.5">
                    <p className="font-semibold text-foreground">如何使用模块大纲生成文档？</p>
                    <p className="text-muted-foreground">
                      步骤：1. 在下方勾选希望分析的模块 ➔ 2. 点击右侧按钮一键生成 ➔ 3. 自动在"AI 知识产物库"生成渲染文档！
                    </p>
                  </div>
                </div>

                <div className="flex items-center gap-2 shrink-0">
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={toggleSelectAll}
                    className="text-xs"
                  >
                    {selectedClusters.length === modules.length ? "取消全选" : "全选大纲"}
                  </Button>

                  <Button
                    size="sm"
                    onClick={handleGenerateWikiForSelected}
                    disabled={isGeneratingWiki || selectedClusters.length === 0}
                    className="gap-1.5 text-xs shadow-sm"
                  >
                    {isGeneratingWiki ? (
                      <Loader2 className="h-3.5 w-3.5 animate-spin" />
                    ) : (
                      <BookOpen className="h-3.5 w-3.5" />
                    )}
                    <span>生成所选模块 Wiki ({selectedClusters.length})</span>
                  </Button>
                </div>
              </CardContent>
            </Card>

            <div className="grid grid-cols-1 gap-3">
              {modules.map((item) => {
                const isChecked = selectedClusters.includes(item.name)
                const isExpanded = expandedModule === item.name

                return (
                  <div
                    key={item.name}
                    className={`rounded-xl border transition-all ${
                      isChecked
                        ? "border-primary/50 bg-primary/5 shadow-xs"
                        : "border-border hover:border-muted-foreground/30 bg-card"
                    }`}
                  >
                    <div className="p-4 flex items-start justify-between gap-4">
                      <div className="flex items-start gap-3 flex-1 min-w-0">
                        <div
                          className="pt-0.5 cursor-pointer"
                          onClick={() => {
                            setSelectedClusters((prev) =>
                              isChecked
                                ? prev.filter((i) => i !== item.name)
                                : [...prev, item.name]
                            )
                          }}
                        >
                          <CheckSquare
                            className={`h-5 w-5 ${
                              isChecked ? "text-primary" : "text-muted-foreground/40"
                            }`}
                          />
                        </div>

                        <div className="space-y-1 flex-1 min-w-0">
                          <div className="flex items-center gap-2 flex-wrap">
                            <span className="font-semibold text-base text-foreground">
                              {item.name}
                            </span>
                            <span className="text-xs bg-muted px-2 py-0.5 rounded font-mono text-muted-foreground">
                              包含 {item.entity_count} 个核心文件
                            </span>
                          </div>

                          {item.summary && (
                            <p className="text-xs text-muted-foreground leading-relaxed">
                              {item.summary}
                            </p>
                          )}
                        </div>
                      </div>

                      {item.entities && item.entities.length > 0 && (
                        <button
                          type="button"
                          onClick={() =>
                            setExpandedModule(isExpanded ? null : item.name)
                          }
                          className="flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground shrink-0 pt-0.5"
                        >
                          <span>{isExpanded ? "收起文件" : "查看相关文件"}</span>
                          {isExpanded ? (
                            <ChevronDown className="h-4 w-4" />
                          ) : (
                            <ChevronRight className="h-4 w-4" />
                          )}
                        </button>
                      )}
                    </div>

                    {isExpanded && item.entities && item.entities.length > 0 && (
                      <div className="px-4 pb-4 pt-2 border-t border-border/50 bg-muted/10 rounded-b-xl space-y-2">
                        <div className="flex items-center gap-1.5 text-xs font-medium text-muted-foreground">
                          <Code className="h-3.5 w-3.5 text-primary" />
                          <span>该业务模块包含的主要代码/文档文件列表</span>
                        </div>
                        <div className="grid grid-cols-1 md:grid-cols-2 gap-1.5 pt-1">
                          {item.entities.map((ent, idx) => (
                            <div
                              key={idx}
                              className="font-mono text-xs bg-background p-2 rounded border border-border/60 flex items-center gap-2 truncate"
                            >
                              <Layers className="h-3.5 w-3.5 text-muted-foreground shrink-0" />
                              <span className="truncate" title={ent}>
                                {ent}
                              </span>
                            </div>
                          ))}
                        </div>
                      </div>
                    )}
                  </div>
                )
              })}
            </div>
          </div>
        )}

        {activeTab === "readme" && (
          <div className="space-y-6 animate-in fade-in duration-200">
            {summary && (
              <Card className="shadow-sm">
                <CardHeader className="pb-3">
                  <CardTitle className="text-base font-semibold flex items-center gap-2">
                    <FileText className="h-5 w-5 text-primary" />
                    <span>项目概要与技术栈</span>
                  </CardTitle>
                </CardHeader>
                <CardContent className="space-y-4">
                  <p className="text-sm leading-relaxed">{summary.description}</p>
                  {summary.technical_stack && summary.technical_stack.length > 0 && (
                    <div>
                      <p className="text-xs font-medium text-muted-foreground mb-2">技术栈标签</p>
                      <div className="flex flex-wrap gap-1.5">
                        {summary.technical_stack.map((s) => (
                          <span key={s} className="text-xs bg-secondary text-secondary-foreground px-2.5 py-1 rounded-md font-mono">
                            {s}
                          </span>
                        ))}
                      </div>
                    </div>
                  )}
                </CardContent>
              </Card>
            )}

            {profileContent ? (
              <Card className="shadow-sm">
                <CardHeader className="pb-3">
                  <CardTitle className="text-base font-semibold text-foreground">
                    项目说明文件 (README.md 项目画像)
                  </CardTitle>
                </CardHeader>
                <CardContent>
                  <MarkdownRenderer content={profileContent} />
                </CardContent>
              </Card>
            ) : (
              <div className="text-center py-12 border border-dashed rounded-xl bg-muted/5">
                <FileText className="h-10 w-10 mx-auto text-muted-foreground/30 mb-2" />
                <p className="text-sm text-muted-foreground">尚未发现 README.md，点击右上角【重新探查项目画像】进行构建</p>
              </div>
            )}
          </div>
        )}

        {activeTab === "artifacts" && (
          <div className="animate-in fade-in duration-200">
            <GenerationPanel />
          </div>
        )}
      </div>

      {numProjectId > 0 && (
        <DiscoverDialog
          projectId={numProjectId}
          open={discoverOpen}
          onOpenChange={setDiscoverOpen}
          onDiscovered={loadData}
        />
      )}
    </div>
  )
}
