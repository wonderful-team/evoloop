import type { MessageReference } from "@/components/Chat/ChatMessageItem"
import { OpenAPI } from "@/client"

export function isAbsolutePath(path: string): boolean {
  return (
    path.startsWith("/") || path.startsWith("~") || /^[a-zA-Z]:[\\/]/.test(path)
  )
}

export function getFileName(path: string): string {
  return path.split("/").pop() || path
}

export function cleanFileUrl(href: string): string {
  return href.replace(/^file:\/\//, "")
}

/**
 * Resolve a local file reference to a renderable <img src>.
 *
 * Raw `file://` URLs are blocked by browsers (and Tauri's asset protocol does
 * not cover arbitrary project paths), so we proxy through the backend
 * `/api/v1/files/raw` endpoint — which enforces the same allowed-root security
 * boundary as the Agent tools (WORKSPACE_ROOT, ~/.evoloop, uploads).
 */
export function resolveLocalFileSrc(src: string): string {
  // 绝对资源 URL / 内联数据 / blob → 原样使用
  if (
    src.startsWith("http://") ||
    src.startsWith("https://") ||
    src.startsWith("data:") ||
    src.startsWith("blob:")
  ) {
    return src
  }
  // 已拼好的后端 API URL（用户上传附件的常见形态）→ 前缀 BASE
  if (src.startsWith("/api/")) {
    return `${OpenAPI.BASE}${src}`
  }
  // file:// 本地路径 → 去协议后包装成 raw 端点
  if (src.startsWith("file://")) {
    return getRawFileUrl(cleanFileUrl(src), undefined, OpenAPI.BASE)
  }
  // uploads/... 或项目相对路径 → 包装成 raw 端点
  return getRawFileUrl(src, undefined, OpenAPI.BASE)
}

export function getRawFileUrl(
  path: string,
  projectId?: number,
  apiBase = "",
): string {
  if (isAbsolutePath(path) || path.startsWith("uploads/")) {
    return `${apiBase}/api/v1/files/raw?path=${encodeURIComponent(path)}`
  }
  return `${apiBase}/api/v1/files/raw?project_id=${projectId ?? 0}&path=${encodeURIComponent(path)}`
}

export interface PreviewTarget {
  path: string
  name: string
  isExternal: boolean
}

export function resolveReferencePreview(
  ref: Pick<
    MessageReference,
    "type" | "target_id" | "target_name" | "meta_data"
  >,
): PreviewTarget | null {
  if (ref.type === "file" || ref.type === "directory") {
    const path =
      ref.meta_data?.source_path ||
      ref.meta_data?.source_id ||
      cleanFileUrl(ref.target_id)
    return {
      path,
      name: ref.target_name || getFileName(path),
      isExternal: isAbsolutePath(path),
    }
  }

  if (ref.type === "image" || ref.type === "audio") {
    const path =
      ref.meta_data?.source_path ||
      ref.meta_data?.source_id ||
      cleanFileUrl(ref.target_id)
    return {
      path,
      name: ref.target_name || getFileName(path),
      isExternal: isAbsolutePath(path),
    }
  }

  return null
}

export function resolveHrefPreview(
  href: string,
  linkText?: string,
): PreviewTarget | null {
  if (href.startsWith("file://") || href.startsWith("~")) {
    const path = cleanFileUrl(href)
    return {
      path,
      name: linkText || getFileName(path),
      isExternal: isAbsolutePath(path),
    }
  }

  if (href.startsWith("uploads/")) {
    return {
      path: href,
      name: linkText || getFileName(href),
      isExternal: false,
    }
  }

  return null
}
