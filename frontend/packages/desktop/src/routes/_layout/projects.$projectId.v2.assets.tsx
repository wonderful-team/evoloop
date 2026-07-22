import { createFileRoute, useParams } from "@tanstack/react-router"
import { Code2, FolderTree, Network, ShieldCheck } from "lucide-react"
import { useState } from "react"
import { FilePreview } from "@/components/Files/FilePreview"
import { FileTree } from "@/components/Files/FileTree"
import { CognitionBar } from "@/components/Projects/Redesign/CognitionBar"

export const Route = createFileRoute("/_layout/projects/$projectId/v2/assets")({
  component: AssetsPage,
})

function AssetsPage() {
  const { projectId } = useParams({ from: "/_layout/projects/$projectId" })
  const [selectedFile, setSelectedFile] = useState<{ path: string; name: string } | null>(null)
  const [activeCanvas, setActiveCanvas] = useState<"code" | "topology">("code")

  const numProjectId = Number(projectId)

  return (
    <div className="flex flex-col h-full w-full overflow-hidden">
      <CognitionBar />

      <div className="flex-1 flex overflow-hidden">
        <div className="w-64 border-r border-border bg-muted/5 flex flex-col shrink-0">
          <div className="h-10 px-3 border-b border-border flex items-center justify-between text-xs font-semibold text-muted-foreground shrink-0">
            <div className="flex items-center gap-2">
              <FolderTree className="h-4 w-4 text-primary" />
              <span>资产与符号目录树</span>
            </div>
          </div>
          <div className="flex-1 overflow-y-auto">
            {numProjectId > 0 && (
              <FileTree
                projectId={numProjectId}
                activePath={selectedFile?.path}
                onSelectFile={(node) => {
                  if (node.type === "file") {
                    setSelectedFile({ path: node.path, name: node.name })
                  }
                }}
              />
            )}
          </div>
        </div>

        <div className="flex-1 flex flex-col overflow-hidden bg-background">
          <div className="h-10 px-4 border-b border-border flex items-center justify-between bg-muted/10 shrink-0">
            <div className="flex items-center gap-2 text-xs font-medium truncate">
              <Code2 className="h-3.5 w-3.5 text-primary shrink-0" />
              <span className="truncate">{selectedFile?.path || "选择左侧文件节点开始预览"}</span>
            </div>
            <div className="flex items-center gap-1 bg-muted/40 p-0.5 rounded border border-border shrink-0">
              <button
                onClick={() => setActiveCanvas("code")}
                className={`px-2 py-0.5 text-xs rounded transition-colors ${
                  activeCanvas === "code"
                    ? "bg-background text-foreground font-medium shadow-sm"
                    : "text-muted-foreground"
                }`}
              >
                预览 / 编辑器
              </button>
              <button
                onClick={() => setActiveCanvas("topology")}
                className={`px-2 py-0.5 text-xs rounded transition-colors ${
                  activeCanvas === "topology"
                    ? "bg-background text-foreground font-medium shadow-sm"
                    : "text-muted-foreground"
                }`}
              >
                CodeRelation 拓扑图
              </button>
            </div>
          </div>

          <div className="flex-1 overflow-hidden relative">
            {activeCanvas === "code" ? (
              <FilePreview projectId={numProjectId} file={selectedFile} />
            ) : (
              <div className="h-full flex flex-col items-center justify-center text-muted-foreground font-sans p-6">
                <Network className="h-12 w-12 mb-3 text-primary opacity-40 animate-pulse" />
                <h4 className="font-medium text-foreground text-sm">CodeRelation 依赖拓扑网络</h4>
                <p className="text-xs text-muted-foreground max-w-sm text-center mt-1">
                  {selectedFile
                    ? `正在展示文件 ${selectedFile.name} 及其代码符号在数据库中的上下游依赖连通节点`
                    : "请先从左侧选取文件节点以分析其依赖拓扑网络"}
                </p>
              </div>
            )}
          </div>
        </div>

        <div className="w-72 border-l border-border bg-muted/5 flex flex-col shrink-0">
          <div className="h-10 px-3 border-b border-border flex items-center gap-2 text-xs font-semibold text-muted-foreground shrink-0">
            <ShieldCheck className="h-4 w-4 text-emerald-500" />
            <span>AI 事实与防幻觉 Inspector</span>
          </div>
          <div className="flex-1 p-3 text-xs space-y-4 overflow-y-auto">
            <div>
              <p className="text-[11px] font-medium text-muted-foreground mb-1">选定文件资产</p>
              <p className="font-mono bg-muted p-2 rounded text-[11px] break-all">
                {selectedFile?.path || "未选择文件"}
              </p>
            </div>
            {selectedFile && (
              <>
                <div>
                  <p className="text-[11px] font-medium text-muted-foreground mb-1">图连通性防幻觉状态</p>
                  <div className="bg-emerald-500/10 border border-emerald-500/20 text-emerald-700 dark:text-emerald-300 p-2.5 rounded flex items-start gap-2">
                    <ShieldCheck className="h-4 w-4 shrink-0 mt-0.5" />
                    <span className="text-[11px] leading-relaxed">
                      包含经 AST 解析验证的代码符号 (EXTRACTED)
                    </span>
                  </div>
                </div>
                <div>
                  <p className="text-[11px] font-medium text-muted-foreground mb-1">关联业务维度</p>
                  <div className="space-y-1">
                    <span className="inline-block text-[10px] bg-secondary text-secondary-foreground px-2 py-0.5 rounded mr-1">
                      CodeChunk 向量块
                    </span>
                    <span className="inline-block text-[10px] bg-secondary text-secondary-foreground px-2 py-0.5 rounded">
                      AST Tree-sitter
                    </span>
                  </div>
                </div>
              </>
            )}
          </div>
        </div>
      </div>
    </div>
  )
}
