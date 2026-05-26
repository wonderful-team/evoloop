import { useQuery } from "@tanstack/react-query"
import { renderAsync } from "docx-preview"
import {
  ExternalLink,
  FileCode,
  FileSpreadsheet,
  FileText,
  Loader2,
} from "lucide-react"
import { useEffect, useRef } from "react"
import { useTranslation } from "react-i18next"
import ReactMarkdown from "react-markdown"
import { Prism as SyntaxHighlighter } from "react-syntax-highlighter"
import { vscDarkPlus } from "react-syntax-highlighter/dist/esm/styles/prism"
import remarkGfm from "remark-gfm"
import { toast } from "sonner"
import * as XLSX from "xlsx"
import { FilesService, OpenAPI } from "@/client"
import { Button } from "@evoloop/shared/components/ui/button"

export interface FilePreviewProps {
  projectId: number
  file: { path: string; name: string } | null
}

export function FilePreview({ projectId, file }: FilePreviewProps) {
  const containerRef = useRef<HTMLDivElement>(null)
  const { t } = useTranslation()

  const getFileType = (name: string) => {
    const ext = name.split(".").pop()?.toLowerCase()
    if (["png", "jpg", "jpeg", "gif", "svg", "webp"].includes(ext || ""))
      return "image"
    if (ext === "pdf") return "pdf"
    if (["docx"].includes(ext || "")) return "docx"
    if (["xlsx"].includes(ext || "")) return "xlsx"
    if (["csv"].includes(ext || "")) return "csv"
    if (["md", "markdown"].includes(ext || "")) return "markdown"
    return "text"
  }

  const getLanguage = (name: string) => {
    const ext = name.split(".").pop()?.toLowerCase() || ""
    const map: Record<string, string> = {
      js: "javascript", jsx: "jsx", ts: "typescript", tsx: "tsx",
      py: "python", sh: "bash", bash: "bash", zsh: "bash",
      yml: "yaml", yaml: "yaml", md: "markdown", html: "markup",
      css: "css", json: "json", java: "java", c: "c", cpp: "cpp",
      go: "go", rs: "rust", sql: "sql", php: "php", rb: "ruby",
      xml: "markup", vue: "markup", svelte: "markup", toml: "toml",
      ini: "ini", env: "ini", dockerfile: "dockerfile"
    }
    return map[ext] || ext || "text"
  }

  const fileType = file ? getFileType(file.name) : "text"
  const isText = fileType === "text" || fileType === "markdown" || fileType === "csv"

  const { data: fileContent, isLoading: isContentLoading } = useQuery({
    queryKey: ["fileContent", projectId, file?.path],
    queryFn: () =>
      FilesService.getFileContent({
        projectId: Number(projectId),
        path: file!.path,
      }),
    enabled: !!file && projectId !== undefined && isText,
    retry: false,
  })

  const rawUrl = file
    ? `${OpenAPI.BASE}/api/v1/projects/${projectId}/files/raw?path=${encodeURIComponent(file.path)}`
    : ""

  useEffect(() => {
    if (!file) return
    if (!containerRef.current) return

    const render = async () => {
      containerRef.current!.innerHTML = ""

      if (fileType === "docx") {
        try {
          const res = await fetch(rawUrl)
          if (!res.ok) throw new Error("Failed to load file")
          const blob = await res.blob()
          await renderAsync(blob, containerRef.current!)
        } catch (e) {
          console.error(e)
          containerRef.current!.innerHTML = `<div class="p-4 text-red-500">Failed to render DOCX preview.</div>`
        }
      } else if (fileType === "xlsx") {
        try {
          const res = await fetch(rawUrl)
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
          containerRef.current!.innerHTML = `<div class="p-4 text-red-500">${t("sidebar.excelPreviewError", "Excel preview error")}</div>`
        }
      } else if (fileType === "csv" && fileContent) {
        try {
          const wb = XLSX.read((fileContent as any).content, { type: "string" })
          const wsName = wb.SheetNames[0]
          const ws = wb.Sheets[wsName]
          const html = XLSX.utils.sheet_to_html(ws)
          containerRef.current!.innerHTML = `<div class="p-4 overflow-auto prose prose-slate max-w-none">${html}</div>`
        } catch (e) {
          console.error(e)
          containerRef.current!.innerHTML = `<div class="p-4 text-red-500">${t("sidebar.csvPreviewError", "CSV preview error")}</div>`
        }
      }
    }
    render()
  }, [file, fileType, rawUrl, fileContent])

  const handleOpenInApp = async () => {
    if (!file) return
    try {
      await FilesService.openFile({
        projectId: Number(projectId),
        requestBody: { path: file.path },
      })
      toast.success(t("files.openExternal", "Opened in external app"))
    } catch (error) {
      console.error(error)
      toast.error(t("files.openExternalError", "Failed to open external app"))
    }
  }

  if (!file) {
    return (
      <div className="flex-1 flex flex-col items-center justify-center text-muted-foreground/50 bg-muted/5 h-full">
        <FileCode className="h-16 w-16 mb-4 opacity-10" />
        <p>{t("files.selectFileToView", "Select a file to view")}</p>
      </div>
    )
  }

  return (
    <div className="h-full flex flex-col bg-background min-w-0">
      <div className="h-10 border-b px-4 flex items-center gap-2 bg-muted/5 text-sm shrink-0">
        {fileType === "image" && <FileCode className="h-4 w-4 text-muted-foreground" />}
        {fileType === "pdf" && <FileText className="h-4 w-4 text-muted-foreground" />}
        {fileType === "xlsx" && <FileSpreadsheet className="h-4 w-4 text-muted-foreground" />}
        {fileType === "csv" && <FileSpreadsheet className="h-4 w-4 text-muted-foreground" />}
        {fileType === "docx" && <FileText className="h-4 w-4 text-muted-foreground" />}
        {fileType === "markdown" && <FileCode className="h-4 w-4 text-muted-foreground" />}
        {fileType === "text" && <FileCode className="h-4 w-4 text-muted-foreground" />}
        <span className="font-medium truncate max-w-[200px]" title={file.name}>{file.name}</span>
        <span
          className="text-xs text-muted-foreground ml-auto opacity-50 font-mono truncate max-w-[300px]"
          title={file.path}
        >
          {file.path}
        </span>

        <div className="ml-2 border-l border-border pl-2 shrink-0">
          <Button
            variant="ghost"
            size="icon"
            className="h-7 w-7"
            onClick={handleOpenInApp}
            title={t("sidebar.openInSystemApp", "Open in system default app")}
          >
            <ExternalLink className="h-4 w-4" />
          </Button>
        </div>
      </div>
      <div className="flex-1 overflow-auto p-0 relative bg-white/50 dark:bg-black/50">
        {fileType === "image" ? (
          <div className="flex items-center justify-center p-4 min-h-full">
            <img
              src={rawUrl}
              alt={file.name}
              className="max-w-full max-h-full object-contain shadow-sm border rounded"
            />
          </div>
        ) : fileType === "pdf" ? (
          <iframe
            key="pdf"
            src={rawUrl}
            className="w-full h-full"
            title={t("files.pdfPreview", "PDF Preview")}
          />
        ) : fileType === "docx" || fileType === "xlsx" || fileType === "csv" ? (
          <div
            key="manual-render"
            ref={containerRef}
            className="w-full h-full overflow-auto bg-white p-4"
          />
        ) : isContentLoading ? (
          <div key="loading" className="h-full flex items-center justify-center text-muted-foreground text-sm">
            <Loader2 className="h-4 w-4 animate-spin mr-2" />
            {t("files.loadingContent", "Loading content...")}
          </div>
        ) : fileType === "markdown" ? (
          <div key="markdown" className="p-8 prose prose-slate dark:prose-invert max-w-none overflow-auto h-full">
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
          <div key="text" className="h-full overflow-auto relative bg-[#1e1e1e]">
            {!(fileContent as any)?.content && !isContentLoading && (
              <div className="text-center text-muted-foreground mt-10">
                {t("files.previewNotAvailable", "Preview not available")}
                <br />
                <a
                  href={rawUrl}
                  target="_blank"
                  rel="noreferrer"
                  className="text-primary hover:underline mt-2 inline-block"
                >
                  {t("files.downloadFile", "Download File")}
                </a>
              </div>
            )}
            {(fileContent as any)?.content && (
              <SyntaxHighlighter
                // @ts-expect-error
                style={vscDarkPlus}
                language={file ? getLanguage(file.name) : "text"}
                PreTag="div"
                customStyle={{ margin: 0, padding: '1rem', background: 'transparent', minHeight: '100%', fontSize: '13px' }}
                showLineNumbers
              >
                {(fileContent as any)?.content || ""}
              </SyntaxHighlighter>
            )}
          </div>
        )}
      </div>
    </div>
  )
}
