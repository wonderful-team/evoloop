import { useTheme } from "@evoloop/shared/components/theme-provider"
import { Button } from "@evoloop/shared/components/ui/button"
import i18n from "@evoloop/shared/i18n"
import Editor from "@monaco-editor/react"
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
import { toast } from "sonner"
import * as XLSX from "xlsx"
import { FilesService, OpenAPI } from "@/client"
import { MarkdownRenderer } from "@/components/Common/MarkdownRenderer"
import { downloadFile } from "@/utils/fileLinkHandler"
import { getRawFileUrl } from "@/utils/fileUtils"

export interface FilePreviewProps {
  projectId: number
  file: { path: string; name: string } | null
}

export function FilePreview({ projectId, file }: FilePreviewProps) {
  const containerRef = useRef<HTMLDivElement>(null)
  const { t } = useTranslation()
  const { resolvedTheme } = useTheme()

  const getFileType = (name: string) => {
    const ext = name.split(".").pop()?.toLowerCase()
    if (["png", "jpg", "jpeg", "gif", "svg", "webp"].includes(ext || ""))
      return "image"
    if (ext === "pdf") return "pdf"
    if (["docx"].includes(ext || "")) return "docx"
    if (["xlsx"].includes(ext || "")) return "xlsx"
    if (["csv"].includes(ext || "")) return "csv"
    if (["md", "markdown"].includes(ext || "")) return "markdown"
    if (["mp3", "wav", "ogg", "m4a", "flac", "aac"].includes(ext || ""))
      return "audio"
    if (["mp4", "webm", "mov", "mkv", "avi", "m4v"].includes(ext || ""))
      return "video"
    return "text"
  }

  const getLanguage = (name: string) => {
    const ext = name.split(".").pop()?.toLowerCase() || ""
    const map: Record<string, string> = {
      js: "javascript",
      jsx: "javascript",
      ts: "typescript",
      tsx: "typescript",
      py: "python",
      sh: "shell",
      bash: "shell",
      zsh: "shell",
      yml: "yaml",
      yaml: "yaml",
      md: "markdown",
      html: "html",
      css: "css",
      json: "json",
      java: "java",
      c: "c",
      cpp: "cpp",
      go: "go",
      rs: "rust",
      sql: "sql",
      php: "php",
      rb: "ruby",
      xml: "xml",
      vue: "html",
      svelte: "html",
      toml: "ini",
      ini: "ini",
      env: "ini",
      dockerfile: "dockerfile",
    }
    return map[ext] || ext || "text"
  }

  const isAbsolutePath = (path: string) =>
    path.startsWith("/") || path.startsWith("~") || /^[a-zA-Z]:[\\/]/.test(path)

  // 文件类型必须由路径/URL 推导（含扩展名）；
  // name 仅作展示（如 "generated image" 无扩展名，会误判为 text）
  const fileType = file ? getFileType(file.path || file.name) : "text"
  const isText =
    fileType === "text" || fileType === "markdown" || fileType === "csv"

  const { data: fileContent, isLoading: isContentLoading } = useQuery({
    queryKey: ["fileContent", projectId, file?.path],
    queryFn: () => {
      if (!file) throw new Error(t("files.noFile"))
      if (isAbsolutePath(file.path)) {
        return FilesService.readAnyFile({
          requestBody: { path: file.path },
        })
      }
      return FilesService.getFileContent({
        projectId: Number(projectId),
        path: file.path,
      })
    },
    enabled: !!file && projectId !== undefined && isText,
    retry: false,
  })

  const rawUrl = file ? getRawFileUrl(file.path, projectId, OpenAPI.BASE) : ""

  useEffect(() => {
    if (!file) return
    if (!containerRef.current) return

    const render = async () => {
      containerRef.current!.innerHTML = ""

      if (fileType === "docx") {
        try {
          const res = await fetch(rawUrl)
          if (!res.ok) throw new Error(t("files.failedToLoadFile"))
          const blob = await res.blob()
          await renderAsync(blob, containerRef.current!)
        } catch (e) {
          console.error(e)
          containerRef.current!.innerHTML = `<div class="p-4 text-red-500">${i18n.t("files.docxPreviewError")}</div>`
        }
      } else if (fileType === "xlsx") {
        try {
          const res = await fetch(rawUrl)
          if (!res.ok) throw new Error(t("files.failedToLoadFile"))
          const blob = await res.blob()
          const buffer = await blob.arrayBuffer()
          const wb = XLSX.read(buffer, { type: "array" })
          const wsName = wb.SheetNames[0]
          const ws = wb.Sheets[wsName]
          const html = XLSX.utils.sheet_to_html(ws)
          containerRef.current!.innerHTML = `<div class="p-4 overflow-auto">${html}</div>`
        } catch (e) {
          console.error(e)
          containerRef.current!.innerHTML = `<div class="p-4 text-red-500">${t("sidebar.excelPreviewError")}</div>`
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
          containerRef.current!.innerHTML = `<div class="p-4 text-red-500">${t("sidebar.csvPreviewError")}</div>`
        }
      }
    }
    render()
  }, [file, fileType, rawUrl, fileContent])

  const handleOpenInApp = async () => {
    if (!file || isAbsolutePath(file.path)) return
    try {
      await FilesService.openFile({
        projectId: Number(projectId),
        requestBody: { path: file.path },
      })
      toast.success(t("files.openExternal"))
    } catch (error) {
      console.error(error)
      toast.error(t("files.openExternalError"))
    }
  }

  if (!file) {
    return (
      <div className="flex-1 flex flex-col items-center justify-center text-muted-foreground/50 bg-muted/5 h-full">
        <FileCode className="h-16 w-16 mb-4 opacity-10" />
        <p>{t("files.selectFileToView")}</p>
      </div>
    )
  }

  return (
    <div className="h-full flex flex-col bg-background min-w-0">
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
        <span className="font-medium truncate max-w-[200px]" title={file.name}>
          {file.name}
        </span>
        <span
          className="text-xs text-muted-foreground ml-auto opacity-50 font-mono truncate max-w-[300px]"
          title={file.path}
        >
          {file.path}
        </span>

        {!isAbsolutePath(file.path) && (
          <div className="ml-2 border-l border-border pl-2 shrink-0">
            <Button
              variant="ghost"
              size="icon"
              className="h-7 w-7"
              onClick={handleOpenInApp}
              title={t("sidebar.openInSystemApp")}
            >
              <ExternalLink className="h-4 w-4" />
            </Button>
          </div>
        )}
      </div>
      <div className="flex-1 overflow-auto p-0 relative bg-background">
        {fileType === "image" ? (
          <div className="flex items-center justify-center p-4 min-h-full">
            {/* max-h-full 在可滚动父容器内会失效（高度由内容撑开），用视口约束防超屏 */}
            <img
              src={rawUrl}
              alt={file.name}
              className="max-w-full max-h-[78vh] w-auto h-auto object-contain shadow-sm border rounded"
            />
          </div>
        ) : fileType === "pdf" ? (
          <iframe
            key="pdf"
            src={rawUrl}
            className="w-full h-full"
            title={t("files.pdfPreview")}
          />
        ) : fileType === "docx" || fileType === "xlsx" || fileType === "csv" ? (
          <div
            key="manual-render"
            ref={containerRef}
            className="w-full h-full overflow-auto bg-white p-4"
          />
        ) : fileType === "audio" ? (
          <div className="flex items-center justify-center p-4 min-h-full">
            {/* biome-ignore lint/a11y/useMediaCaption: 通用音频预览，无预生成字幕轨道 */}
            <audio
              controls
              src={rawUrl}
              className="w-full max-w-md"
              preload="metadata"
            >
              {t(
                "chat.messageList.audioNotSupported",
                "Your browser does not support audio playback",
              )}
            </audio>
          </div>
        ) : fileType === "video" ? (
          <div className="flex items-center justify-center p-4 min-h-full">
            {/* biome-ignore lint/a11y/useMediaCaption: 通用视频预览，无预生成字幕轨道 */}
            <video
              controls
              src={rawUrl}
              className="max-w-full max-h-full rounded border bg-black"
              preload="metadata"
            >
              {t(
                "chat.messageList.videoNotSupported",
                "Your browser does not support video playback",
              )}
            </video>
          </div>
        ) : isContentLoading ? (
          <div
            key="loading"
            className="h-full flex items-center justify-center text-muted-foreground text-sm"
          >
            <Loader2 className="h-4 w-4 animate-spin mr-2" />
            {t("files.loadingContent")}
          </div>
        ) : fileType === "markdown" ? (
          (fileContent as any)?.content?.length > 50000 ? (
            <div
              key="markdown-fallback"
              className="p-4 dark:bg-[#1e1e1e] dark:text-[#d4d4d4] bg-zinc-50 text-zinc-900 font-mono text-[13px] whitespace-pre min-h-full overflow-auto"
            >
              {(fileContent as any).content}
            </div>
          ) : (
            <div key="markdown" className="p-8 overflow-auto h-full">
              <MarkdownRenderer content={(fileContent as any)?.content || ""} />
            </div>
          )
        ) : (
          <div
            key="text"
            className="h-full overflow-hidden relative dark:bg-[#1e1e1e] bg-zinc-50"
          >
            {!(fileContent as any)?.content && !isContentLoading && (
              <div className="text-center text-muted-foreground mt-10">
                {t("files.previewNotAvailable")}
                <br />
                <button
                  type="button"
                  onClick={() => downloadFile(file?.path || "", projectId)}
                  className="text-primary hover:underline mt-2 inline-block cursor-pointer"
                >
                  {t("files.downloadFile")}
                </button>
              </div>
            )}
            {(fileContent as any)?.content && (
              <Editor
                height="100%"
                language={file ? getLanguage(file.name) : "text"}
                theme={resolvedTheme === "dark" ? "vs-dark" : "vs"}
                value={(fileContent as any).content}
                options={{
                  readOnly: true,
                  minimap: { enabled: false },
                  scrollBeyondLastLine: false,
                  wordWrap: "on",
                  fontSize: 13,
                  fontFamily: "var(--font-mono)",
                  lineNumbersMinChars: 3,
                  folding: true,
                  domReadOnly: true,
                }}
                loading={
                  <div className="h-full flex items-center justify-center text-muted-foreground text-sm">
                    <Loader2 className="h-4 w-4 animate-spin mr-2" />
                    {t("files.loadingEditor")}
                  </div>
                }
              />
            )}
          </div>
        )}
      </div>
    </div>
  )
}
