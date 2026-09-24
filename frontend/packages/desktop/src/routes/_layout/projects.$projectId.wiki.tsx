import {Button} from "@evoloop/shared/components/ui/button"
import {ResizableHandle, ResizablePanel, ResizablePanelGroup,} from "@evoloop/shared/components/ui/resizable"
import {useMutation, useQuery, useQueryClient} from "@tanstack/react-query"
import {createFileRoute} from "@tanstack/react-router"
import {BookOpen, ChevronDown, ChevronRight, FileText, Folder, Loader2, RefreshCw,} from "lucide-react"
import {useEffect, useMemo, useState} from "react"
import {useTranslation} from "react-i18next"
import {toast} from "sonner"
import {ProjectsService, WikiService} from "@/client"
import {MarkdownRenderer} from "@/components/Common/MarkdownRenderer"
import {useSystemEvent} from "@/hooks/useSystemEvent"

export const Route = createFileRoute("/_layout/projects/$projectId/wiki")({
  component: WikiPage,
})

type WikiPageItem = {
  id: number
  title: string
  slug: string
  content: string
  created_at: string
  parent_id?: number | null
  children?: WikiPageItem[]
}

function buildTree(pages: WikiPageItem[]): WikiPageItem[] {
  const map = new Map<number, WikiPageItem>()
  const roots: WikiPageItem[] = []

  pages.forEach((p) => {
    map.set(p.id, { ...p, children: [] })
  })

  pages.forEach((p) => {
    const node = map.get(p.id)!
    if (p.parent_id) {
      const parent = map.get(p.parent_id)
      if (parent) {
        parent.children?.push(node)
      } else {
        roots.push(node)
      }
    } else {
      roots.push(node)
    }
  })

  return roots
}

function WikiTreeItem({
  node,
  level = 0,
  selectedPage,
  onSelect,
}: {
  node: WikiPageItem
  level?: number
  selectedPage: WikiPageItem | null
  onSelect: (p: WikiPageItem) => void
}) {
  const [isOpen, setIsOpen] = useState(true)
  const hasChildren = node.children && node.children.length > 0

  return (
    <div>
      <button
        onClick={() => {
          onSelect(node)
          if (hasChildren) setIsOpen(!isOpen)
        }}
        className={`flex items-center w-full text-left px-2 py-1.5 rounded text-sm transition-colors ${
          selectedPage?.id === node.id
            ? "bg-primary/10 text-primary font-medium"
            : "hover:bg-muted text-muted-foreground hover:text-foreground"
        }`}
        style={{ paddingLeft: `${level * 12 + 8}px` }}
      >
        {hasChildren ? (
          <span
            className="mr-1 opacity-50 hover:opacity-100 cursor-pointer"
            onClick={(e) => {
              e.stopPropagation()
              setIsOpen(!isOpen)
            }}
          >
            {isOpen ? (
              <ChevronDown className="h-3 w-3" />
            ) : (
              <ChevronRight className="h-3 w-3" />
            )}
          </span>
        ) : (
          <span className="mr-1 w-3" />
        )}

        {hasChildren ? (
          <Folder className="h-3.5 w-3.5 mr-2 opacity-70" />
        ) : (
          <FileText className="h-3.5 w-3.5 mr-2 opacity-70" />
        )}
        <span className="truncate">{node.title}</span>
      </button>

      {hasChildren && isOpen && (
        <div>
          {node.children!.map((child) => (
            <WikiTreeItem
              key={child.id}
              node={child}
              level={level + 1}
              selectedPage={selectedPage}
              onSelect={onSelect}
            />
          ))}
        </div>
      )}
    </div>
  )
}

function WikiPage() {
  const { t } = useTranslation()
  const { projectId } = Route.useParams()
  const queryClient = useQueryClient()
  const [selectedPage, setSelectedPage] = useState<WikiPageItem | null>(null)
  const [wikiStatus, setWikiStatus] = useState<string | null>(null)

  const numProjectId = Number(projectId)

  useEffect(() => {
    const fetchWikiStatus = async () => {
      try {
        const res = await ProjectsService.listGenerationStatusEndpoint({
          projectId: numProjectId,
        })
        const wikiItem = res.items.find((i: any) => i.item === "wiki")
        if (wikiItem) setWikiStatus(wikiItem.status)
      } catch (err) {
        console.error("Failed to fetch initial wiki status", err)
      }
    }
    fetchWikiStatus()
  }, [numProjectId])

  useSystemEvent("generation.status", (event) => {
    if (event.data?.project_id === numProjectId && event.data?.item === "wiki") {
      setWikiStatus(event.data.status)
      if (event.data.status === "completed") {
        queryClient.invalidateQueries({ queryKey: ["wiki"] })
      }
    }
  })

  const { data: pages, isLoading } = useQuery({
    queryKey: ["wiki", projectId],
    queryFn: async () => {
      const res = await WikiService.getWikiPages({
        projectId: numProjectId,
      })
      return res as WikiPageItem[]
    },
  })

  const treeData = useMemo(() => {
    if (!pages) return []
    return buildTree(pages)
  }, [pages])

  const generateMutation = useMutation({
    mutationFn: async () => {
      setWikiStatus("running")
      return WikiService.generateWiki({
        requestBody: {
          project_id: numProjectId,
          topic: t("wiki.topic.full_documentation"),
          force_regenerate: true,
        },
      })
    },
    onSuccess: () => {
      toast.success(t("wiki.toast.start"))
      queryClient.invalidateQueries({ queryKey: ["wiki"] })
    },
    onError: (error: any) => {
      setWikiStatus("failed")
      const isBenefitError =
        error?.status === 403 ||
        error?.body?.detail?.code === "BENEFIT_REQUIRED" ||
        error?.body?.code === "BENEFIT_REQUIRED"

      if (!isBenefitError) {
        toast.error(t("wiki.toast.error"))
      }
    },
  })

  const handleGenerate = () => {
    generateMutation.mutate()
  }

  if (pages && pages.length > 0 && !selectedPage) {
    if (treeData.length > 0 && !selectedPage) {
      setSelectedPage(treeData[0])
    }
  }

  return (
    <ResizablePanelGroup direction="horizontal" className="h-full w-full">
      <ResizablePanel
        defaultSize={20}
        minSize={15}
        maxSize={30}
        className="bg-muted/5 flex flex-col min-w-[200px] border-r"
      >
        <div className="h-10 border-b px-4 flex items-center justify-between bg-muted/5 shrink-0">
          <span className="font-semibold text-sm">{t("wiki.pageList")}</span>
          <Button
            variant="ghost"
            size="icon"
            className="h-7 w-7"
            onClick={() =>
              queryClient.invalidateQueries({ queryKey: ["wiki"] })
            }
          >
            <RefreshCw className="h-3.5 w-3.5" />
          </Button>
        </div>

        <div className="flex-1 overflow-auto p-2 space-y-1">
          {isLoading ? (
            <div className="flex items-center justify-center py-4 text-xs text-muted-foreground">
              {t("common.loading")}
            </div>
          ) : treeData.length > 0 ? (
            treeData.map((node) => (
              <WikiTreeItem
                key={node.id}
                node={node}
                selectedPage={selectedPage}
                onSelect={setSelectedPage}
              />
            ))
          ) : (
            <div className="text-center py-8 px-2">
              <p className="text-xs text-muted-foreground mb-4">
                {t("wiki.noDocs")}
              </p>
              <Button
                size="sm"
                onClick={handleGenerate}
                disabled={generateMutation.isPending || wikiStatus === "running"}
              >
                {generateMutation.isPending || wikiStatus === "running" ? (
                  <Loader2 className="h-3 w-3 animate-spin mr-2" />
                ) : (
                  <BookOpen className="h-3 w-3 mr-2" />
                )}
                {generateMutation.isPending || wikiStatus === "running"
                  ? "Wiki 正在生成中..."
                  : t("wiki.generate")}
              </Button>
            </div>
          )}
        </div>

        {pages && pages.length > 0 && (
          <div className="p-2 border-t">
            <Button
              variant="outline"
              size="sm"
              className="w-full"
              onClick={handleGenerate}
              disabled={generateMutation.isPending || wikiStatus === "running"}
            >
              {generateMutation.isPending || wikiStatus === "running" ? (
                <Loader2 className="h-3 w-3 animate-spin mr-2" />
              ) : (
                <RefreshCw className="h-3 w-3 mr-2" />
              )}
              {generateMutation.isPending || wikiStatus === "running"
                ? "正在重新生成中..."
                : t("wiki.regenerate")}
            </Button>
          </div>
        )}
      </ResizablePanel>

      <ResizableHandle withHandle />

      <ResizablePanel defaultSize={80}>
        <div className="h-full flex flex-col bg-background min-w-0">
          {wikiStatus === "running" && (
            <div className="bg-blue-500/10 text-blue-600 dark:text-blue-400 px-6 py-2 border-b border-blue-500/20 text-xs flex items-center gap-2 shrink-0">
              <Loader2 className="h-3.5 w-3.5 animate-spin" />
              <span>AI 正在后台全力生成/更新百科文档中，您可以继续阅读或查阅现有章节。完成后本页将自动刷新。</span>
            </div>
          )}
          {selectedPage ? (
            <>
              <div className="h-10 border-b px-6 flex items-center bg-white/50 shrink-0">
                <h1 className="font-semibold text-sm">{selectedPage.title}</h1>
                <span className="ml-auto text-xs text-muted-foreground">
                  {t("wiki.lastUpdated")}:{" "}
                  {new Date(selectedPage.created_at).toLocaleDateString()}
                </span>
              </div>
              <div className="flex-1 overflow-auto p-8">
                <MarkdownRenderer content={selectedPage.content} />
              </div>
            </>
          ) : (
            <div className="flex-1 flex flex-col items-center justify-center text-muted-foreground/50 bg-muted/5">
              <BookOpen className="h-16 w-16 mb-4 opacity-10" />
              <p>{t("wiki.selectPage")}</p>
            </div>
          )}
        </div>
      </ResizablePanel>
    </ResizablePanelGroup>
  )
}
