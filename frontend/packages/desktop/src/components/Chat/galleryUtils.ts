import type { Message } from "./ChatMessageItem"

export interface GalleryImage {
  url: string
  name: string
}

/**
 * 收集整个会话（消息列表）的全部图片引用，供会话级 Gallery 使用。
 * - 跨消息按顺序收集（user/ai/tool 均计入）
 * - 按 target_id 去重（同图多消息只保留首次出现）
 * - 跳过非 image 类型与空 target_id
 */
export function collectSessionImages(messages: Message[]): GalleryImage[] {
  const images: GalleryImage[] = []
  const seen = new Set<string>()
  for (const m of messages || []) {
    for (const r of m.references || []) {
      if (r.type === "image" && r.target_id && !seen.has(r.target_id)) {
        seen.add(r.target_id)
        images.push({
          url: r.target_id,
          name: r.target_name || r.target_id,
        })
      }
    }
  }
  return images
}
