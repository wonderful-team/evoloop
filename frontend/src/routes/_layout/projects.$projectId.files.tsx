import { useQuery } from "@tanstack/react-query"
import { createFileRoute } from "@tanstack/react-router"
import { renderAsync } from "docx-preview"
import {
  ExternalLink,
  FileCode,
  FileSpreadsheet,
  FileText,
  Loader2,
} from "lucide-react"
import { useEffect, useRef, useState } from "react"
import ReactMarkdown from "react-markdown"
import { Prism as SyntaxHighlighter } from "react-syntax-highlighter"
import { vscDarkPlus } from "react-syntax-highlighter/dist/esm/styles/prism"
import remarkGfm from "remark-gfm"
import { toast } from "sonner"
import * as XLSX from "xlsx"
import { FilesService, OpenAPI } from "@/client"
import { FileTree } from "@/components/Files/FileTree"
import { Button } from "@/components/ui/button"
import {
  ResizableHandle,
  ResizablePanel,
  ResizablePanelGroup,
} from "@/components/ui/resizable"

export const Route = createFileRoute("/_layout/projects/$projectId/files")({
  component: FilesPage,
})

function FilesPage() {
  const { projectId } = Route.useParams()
  const [selectedFile, setSelectedFile] = useState<{
    path: string
    name: string
  } | null>(null)
  const containerRef = useRef<HTMLDivElement>(null)

  // Determine file type
  const getFileType = (name: string) => {
    const ext = name.split(".").pop()?.toLowerCase()
    if (["png", "jpg", "jpeg", "gif", "svg", "webp"].includes(ext || ""))
      return "image"
    if (ext === "pdf") return "pdf"
    if (["docx"].includes(ext || "")) return "docx"
    if (["xlsx"].includes(ext || "")) return "xlsx"
    if (["csv"].includes(ext || "")) return "csv"
    if (["md", "markdown"].includes(ext || "")) return "markdown"
    // Assume text/code for others or fallback
    return "text"
  }

  const fileType = selectedFile ? getFileType(selectedFile.name) : "text"
  const isText =
    fileType === "text" || fileType === "markdown" || fileType === "csv"

  // Load text content
  const { data: fileContent, isLoading: isContentLoading } = useQuery({
    queryKey: ["fileContent", projectId, selectedFile?.path],
    queryFn: () =>
      FilesService.getFileContent({
        projectId: Number(projectId),
        path: selectedFile!.path,
      }),
    enabled: !!selectedFile && !!projectId && isText,
    retry: false,
  })

  // Construct Raw URL
  const rawUrl = selectedFile
    ? `${OpenAPI.BASE}/api/v1/files/projects/${projectId}/files/raw?path=${encodeURIComponent(selectedFile.path)}`
    : ""

  // Handle Office / Binary rendering manually
  useEffect(() => {
    if (!selectedFile) return
    if (!containerRef.current) return

    const render = async () => {
      // Clear container
      containerRef.current!.innerHTML = ""

      if (fileType === "docx") {
        try {
          const token = localStorage.getItem("access_token")
          const res = await fetch(rawUrl, {
            headers: { Authorization: `Bearer ${token}` },
          })
          if (!res.ok) throw new Error("Failed to load file")
          const blob = await res.blob()
          await renderAsync(blob, containerRef.current!)
        } catch (e) {
          console.error(e)
          containerRef.current!.innerHTML = `<div class="p-4 text-red-500">Failed to render DOCX preview.</div>`
        }
      } else if (fileType === "xlsx") {
        try {
          const token = localStorage.getItem("access_token")
          const res = await fetch(rawUrl, {
            headers: { Authorization: `Bearer ${token}` },
          })
          if (!res.ok) throw new Error("Failed to load file")
          const blob = await res.blob()
          const buffer = await blob.arrayBuffer()
          const wb = XLSX.read(buffer, { type: "array" })
          const wsName = wb.SheetNames[0]
          const ws = wb.Sheets[wsName]
          const html = XLSX.utils.sheet_to_html(ws)
          containerRef.current!.innerHTML = `<div class="p-4 overflow-auto">${html}</div>`
        } catch (e) {
          console.error(e)
          containerRef.current!.innerHTML = `<div class="p-4 text-red-500">Failed to render Excel preview.</div>`
        }
      } else if (fileType === "csv" && fileContent) {
        try {
          // Parse CSV string content
          const wb = XLSX.read((fileContent as any).content, { type: "string" })
          const wsName = wb.SheetNames[0]
          const ws = wb.Sheets[wsName]
          const html = XLSX.utils.sheet_to_html(ws) // Generates simple HTML table

          // Wrap in prose to style it nicely if using typography plugin, or default table styles
          containerRef.current!.innerHTML = `<div class="p-4 overflow-auto prose prose-slate max-w-none">
                        ${html}
                     </div>`
        } catch (e) {
          console.error(e)
          // Fallback will supply text view if this fails, or we can show error
          containerRef.current!.innerHTML = `<div class="p-4 text-red-500">Failed to render CSV table.</div>`
        }
      }
    }
    render()
  }, [selectedFile, fileType, rawUrl, fileContent])

  const handleOpenInApp = async () => {
    if (!selectedFile) return
    try {
      await FilesService.openFile({
        projectId: Number(projectId),
        requestBody: { path: selectedFile.path },
      })
      toast.success("Opening file in external app...")
    } catch (error) {
      console.error(error)
      toast.error("Failed to open file")
    }
  }

  return (
    <ResizablePanelGroup direction="horizontal" className="h-full w-full">
      <ResizablePanel
        defaultSize={20}
        minSize={15}
        maxSize={40}
        className="bg-muted/5 flex flex-col min-w-[200px]"
      >
        <div className="flex-1 overflow-auto py-2">
          <FileTree
            projectId={Number(projectId)}
            onSelectFile={(node) =>
              setSelectedFile({ path: node.path, name: node.name })
            }
          />
        </div>
      </ResizablePanel>

      <ResizableHandle withHandle />

      <ResizablePanel defaultSize={80}>
        <div className="h-full flex flex-col bg-background min-w-0">
          {selectedFile ? (
            <>
              <div className="h-10 border-b px-4 flex items-center gap-2 bg-muted/5 text-sm shrink-0">
                {fileType === "image" && (
                  <FileCode className="h-4 w-4 text-muted-foreground" />
                )}
                {fileType === "pdf" && (
                  <FileText className="h-4 w-4 text-muted-foreground" />
                )}
                {fileType === "xlsx" && (
                  <FileSpreadsheet className="h-4 w-4 text-muted-foreground" />
                )}
                {fileType === "csv" && (
                  <FileSpreadsheet className="h-4 w-4 text-muted-foreground" />
                )}
                {fileType === "docx" && (
                  <FileText className="h-4 w-4 text-muted-foreground" />
                )}
                {fileType === "markdown" && (
                  <FileCode className="h-4 w-4 text-muted-foreground" />
                )}
                {fileType === "text" && (
                  <FileCode className="h-4 w-4 text-muted-foreground" />
                )}

                <span className="font-medium">{selectedFile.name}</span>
                <span
                  className="text-xs text-muted-foreground ml-auto opacity-50 font-mono truncate max-w-[300px]"
                  title={selectedFile.path}
                >
                  {selectedFile.path}
                </span>

                <div className="ml-2 border-l pl-2 shrink-0">
                  <Button
                    variant="ghost"
                    size="icon"
                    className="h-7 w-7"
                    onClick={handleOpenInApp}
                    title="Open in System App"
                  >
                    <ExternalLink className="h-4 w-4" />
                  </Button>
                </div>
              </div>
              <div className="flex-1 overflow-auto p-0 relative bg-white/50">
                {fileType === "image" ? (
                  <div className="flex items-center justify-center p-4 min-h-full">
                    <img
                      src={rawUrl}
                      alt={selectedFile.name}
                      className="max-w-full max-h-full object-contain shadow-sm border rounded"
                    />
                  </div>
                ) : fileType === "pdf" ? (
                  <iframe
                    key="pdf"
                    src={rawUrl}
                    className="w-full h-full"
                    title="PDF Preview"
                  />
                ) : fileType === "docx" ||
                  fileType === "xlsx" ||
                  fileType === "csv" ? (
                  <div
                    key="manual-render"
                    ref={containerRef}
                    className="w-full h-full overflow-auto bg-white p-4"
                  />
                ) : isContentLoading ? (
                  <div
                    key="loading"
                    className="h-full flex items-center justify-center text-muted-foreground text-sm"
                  >
                    <Loader2 className="h-4 w-4 animate-spin mr-2" />
                    Loading content...
                  </div>
                ) : fileType === "markdown" ? (
                  <div
                    key="markdown"
                    className="p-8 prose prose-slate dark:prose-invert max-w-none overflow-auto h-full"
                  >
                    <ReactMarkdown
                      remarkPlugins={[remarkGfm]}
                      components={{
                        code({ node: _node, className, children, ...props }) {
                          const match = /language-(\w+)/.exec(className || "")
                          return match ? (
                            <SyntaxHighlighter
                              // @ts-expect-error
                              style={vscDarkPlus}
                              language={match[1]}
                              PreTag="div"
                              {...props}
                            >
                              {String(children).replace(/\n$/, "")}
                            </SyntaxHighlighter>
                          ) : (
                            <code className={className} {...props}>
                              {children}
                            </code>
                          )
                        },
                      }}
                    >
                      {(fileContent as any)?.content || ""}
                    </ReactMarkdown>
                  </div>
                ) : (
                  <pre
                    key="text"
                    className="p-4 font-mono text-sm text-foreground/90 overflow-auto whitespace-pre-wrap break-all"
                  >
                    {(fileContent as any)?.content || ""}
                    {!(fileContent as any)?.content && !isContentLoading && (
                      <div className="text-center text-muted-foreground mt-10">
                        Preview not available for this file type.
                        <br />
                        <a
                          href={rawUrl}
                          target="_blank"
                          rel="noreferrer"
                          className="text-primary hover:underline mt-2 inline-block"
                        >
                          Download File
                        </a>
                      </div>
                    )}
                  </pre>
                )}
              </div>
            </>
          ) : (
            <div className="flex-1 flex flex-col items-center justify-center text-muted-foreground/50 bg-muted/5">
              <FileCode className="h-16 w-16 mb-4 opacity-10" />
              <p>Select a file to view</p>
            </div>
          )}
        </div>
      </ResizablePanel>
    </ResizablePanelGroup>
  )
}
