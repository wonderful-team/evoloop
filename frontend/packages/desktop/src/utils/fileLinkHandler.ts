import i18n from "@evoloop/shared/i18n"
import {OpenAPI} from "@/client"
import {isTauri} from "@/lib/tauri"
import {isAbsolutePath} from "./fileUtils"

export async function previewFile(path: string, name?: string): Promise<void> {
  const displayName = name || path.split("/").pop() || path
  const { useUIStore } = await import("@/stores/uiStore")
  useUIStore.getState().setPreviewFile({ path, name: displayName })
}

export async function openExternalLink(href: string): Promise<void> {
  if (isTauri()) {
    const url = href.startsWith("http")
      ? href
      : `${window.location.origin}${href}`
    const { open } = await import("@tauri-apps/plugin-shell")
    await open(url)
  } else {
    window.open(href, "_blank", "noopener,noreferrer")
  }
}

export async function downloadFile(
  path: string,
  projectId?: number,
): Promise<void> {
  const apiBase = OpenAPI.BASE

  if (isAbsolutePath(path)) {
    await downloadExternalFile(path, apiBase)
    return
  }

  // 项目内相对路径或 uploads/ 路径：通过 raw endpoint 下载
  const url = `${apiBase}/api/v1/files/raw?project_id=${projectId ?? 0}&path=${encodeURIComponent(path)}`
  const filename = path.split("/").pop() || i18n.t("files.downloadFallback")
  await downloadFromUrl(url, filename)
}

async function downloadExternalFile(
  path: string,
  apiBase: string,
): Promise<void> {
  const url = `${apiBase}/api/v1/files/download`
  const filename = path.split("/").pop() || i18n.t("files.downloadFallback")

  if (isTauri()) {
    try {
      const res = await fetch(url, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ path }),
      })
      if (!res.ok) throw new Error(`Download failed: ${res.status}`)

      const blob = await res.blob()
      const { save } = await import("@tauri-apps/plugin-dialog")
      const { writeFile } = await import("@tauri-apps/plugin-fs")

      const savePath = await save({ defaultPath: filename })
      if (savePath) {
        const bytes = new Uint8Array(await blob.arrayBuffer())
        await writeFile(savePath, bytes)
      }
    } catch (e) {
      console.error("Download failed:", e)
    }
  } else {
    const form = document.createElement("form")
    form.method = "POST"
    form.action = url
    form.target = "_blank"

    const input = document.createElement("input")
    input.type = "hidden"
    input.name = "path"
    input.value = path
    form.appendChild(input)

    document.body.appendChild(form)
    form.submit()
    form.remove()
  }
}

async function downloadFromUrl(url: string, filename: string): Promise<void> {
  if (isTauri()) {
    try {
      const res = await fetch(url)
      if (!res.ok) throw new Error(`Download failed: ${res.status}`)

      const blob = await res.blob()
      const { save } = await import("@tauri-apps/plugin-dialog")
      const { writeFile } = await import("@tauri-apps/plugin-fs")

      const savePath = await save({ defaultPath: filename })
      if (savePath) {
        const bytes = new Uint8Array(await blob.arrayBuffer())
        await writeFile(savePath, bytes)
      }
    } catch (e) {
      console.error("Download failed:", e)
    }
  } else {
    const a = document.createElement("a")
    a.href = url
    a.download = filename
    document.body.appendChild(a)
    a.click()
    a.remove()
  }
}
