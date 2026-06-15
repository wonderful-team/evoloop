import { isTauri } from "@/lib/tauri"

const VOICE_DIR = "voice/recordings"
const MAX_LOCAL_STORAGE_DAYS = 7 // 本地缓存7天

/**
 * 获取语音文件存储目录
 */
export async function getVoiceStoragePath(): Promise<string> {
  if (!isTauri()) {
    return `/mock/${VOICE_DIR}`
  }
  const { appLocalDataDir, join } = await import("@tauri-apps/api/path")
  const appData = await appLocalDataDir()
  return await join(appData, VOICE_DIR)
}

/**
 * 确保语音目录存在
 */
export async function ensureVoiceDirectory(): Promise<string> {
  const dir = await getVoiceStoragePath()
  if (!isTauri()) {
    return dir
  }
  const { exists, mkdir } = await import("@tauri-apps/plugin-fs")
  const dirExists = await exists(dir)
  if (!dirExists) {
    await mkdir(dir, { recursive: true })
  }
  return dir
}

/**
 * 生成语音文件名
 */
export function generateVoiceFilename(extension: string = "webm"): string {
  const timestamp = Date.now()
  const random = Math.random().toString(36).substring(2, 8)
  return `voice_${timestamp}_${random}.${extension}`
}

/**
 * Blob 转 Uint8Array
 */
async function blobToUint8Array(blob: Blob): Promise<Uint8Array> {
  const arrayBuffer = await blob.arrayBuffer()
  return new Uint8Array(arrayBuffer)
}

/**
 * 保存录音文件到本地
 */
export async function saveVoiceRecording(
  blob: Blob,
  filename?: string,
): Promise<{ path: string; url: string }> {
  const name = filename || generateVoiceFilename()

  if (!isTauri()) {
    return {
      path: `blob:${name}`,
      url: URL.createObjectURL(blob),
    }
  }

  const dir = await ensureVoiceDirectory()
  const { join } = await import("@tauri-apps/api/path")
  const { writeFile } = await import("@tauri-apps/plugin-fs")
  const { convertFileSrc } = await import("@tauri-apps/api/core")
  const filePath = await join(dir, name)

  const uint8Array = await blobToUint8Array(blob)
  await writeFile(filePath, uint8Array)

  return {
    path: filePath,
    url: convertFileSrc(filePath),
  }
}

/**
 * 将 WebM 转换为 MP3（通过后端）
 */
export async function convertToMp3(
  inputPath: string,
  outputFilename?: string,
): Promise<{ path: string; url: string }> {
  if (!isTauri()) {
    console.warn("Audio conversion is only available in Tauri mode")
    return { path: inputPath, url: "" }
  }

  try {
    const { invoke } = await import("@tauri-apps/api/core")
    const { convertFileSrc } = await import("@tauri-apps/api/core")
    const result: string = await invoke("convert_audio", {
      inputPath,
      outputFormat: "mp3",
      outputFilename: outputFilename || generateVoiceFilename("mp3"),
    })

    return {
      path: result,
      url: convertFileSrc(result),
    }
  } catch (error) {
    console.warn("Audio conversion failed, using original:", error)
    const { convertFileSrc } = await import("@tauri-apps/api/core")
    return {
      path: inputPath,
      url: convertFileSrc(inputPath),
    }
  }
}

/**
 * 删除本地语音文件
 */
export async function deleteVoiceFile(filePath: string): Promise<void> {
  if (!isTauri()) {
    // In web mode, we can't track blob URLs reliably; just log
    console.log("[voiceStorage] Skipping file deletion in web mode:", filePath)
    return
  }
  try {
    const { exists, remove } = await import("@tauri-apps/plugin-fs")
    const fileExists = await exists(filePath)
    if (fileExists) {
      await remove(filePath)
    }
  } catch (error) {
    console.error("Failed to delete voice file:", error)
  }
}

/**
 * 清理过期的本地语音文件
 */
export async function cleanupExpiredVoiceFiles(): Promise<void> {
  if (!isTauri()) return
  try {
    const dir = await getVoiceStoragePath()
    const { exists } = await import("@tauri-apps/plugin-fs")
    const { invoke } = await import("@tauri-apps/api/core")
    const dirExists = await exists(dir)
    if (!dirExists) return

    // 调用 Rust 命令清理过期文件
    await invoke("cleanup_voice_files", {
      directory: dir,
      maxAgeDays: MAX_LOCAL_STORAGE_DAYS,
    })
  } catch (error) {
    console.error("Failed to cleanup voice files:", error)
  }
}

/**
 * 格式化时长显示
 */
export function formatDuration(seconds: number): string {
  if (seconds < 60) {
    return `0:${String(seconds).padStart(2, "0")}`
  }
  const mins = Math.floor(seconds / 60)
  const secs = seconds % 60
  return `${mins}:${String(secs).padStart(2, "0")}`
}

/**
 * 获取音频时长
 */
export function getAudioDuration(blob: Blob): Promise<number> {
  return new Promise((resolve) => {
    const audio = new Audio()
    const url = URL.createObjectURL(blob)

    audio.addEventListener("loadedmetadata", () => {
      URL.revokeObjectURL(url)
      resolve(Math.floor(audio.duration))
    })

    audio.addEventListener("error", () => {
      URL.revokeObjectURL(url)
      resolve(0)
    })

    // 3秒超时
    setTimeout(() => {
      URL.revokeObjectURL(url)
      resolve(0)
    }, 3000)

    audio.src = url
  })
}

/**
 * 从 URL 或路径获取文件名
 */
export function getFilenameFromPath(path: string): string {
  const parts = path.split(/[/\\]/)
  return parts[parts.length - 1] || "unknown"
}
