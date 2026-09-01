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
  if (!src.startsWith("file://")) return src
  return getRawFileUrl(cleanFileUrl(src), undefined, OpenAPI.BASE)
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
