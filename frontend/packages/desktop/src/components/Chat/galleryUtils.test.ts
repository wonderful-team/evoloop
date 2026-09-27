import {describe, expect, it} from "vitest"

import type {Message} from "./ChatMessageItem"
import {collectSessionImages} from "./galleryUtils"

function msg(
  id: string,
  role: Message["role"],
  references: any[] | undefined,
): Message {
  return {
    id,
    role,
    content: `content-${id}`,
    timestamp: new Date().toISOString(),
    status: "completed",
    changeset_count: 0,
    references,
  } as Message
}

const img = (url: string, name = "generated image") => ({
  type: "image",
  target_id: url,
  target_name: name,
})

describe("collectSessionImages", () => {
  it("collects image references across user and ai messages in order", () => {
    const messages = [
      msg("m1", "human", [
        img("https://x.com/up1.jpg", "up1.jpg"),
        img("https://x.com/up2.jpg", "up2.jpg"),
      ]),
      msg("m2", "tool", [img("https://x.com/ignored.png")]), // tool 消息也计入
      msg("m3", "ai", [img("https://x.com/gen1.png")]),
    ]
    const images = collectSessionImages(messages)
    expect(images.map((i) => i.url)).toEqual([
      "https://x.com/up1.jpg",
      "https://x.com/up2.jpg",
      "https://x.com/ignored.png",
      "https://x.com/gen1.png",
    ])
  })

  it("deduplicates identical target_ids across messages", () => {
    const messages = [
      msg("m1", "ai", [img("https://x.com/same.png")]),
      msg("m2", "ai", [img("https://x.com/same.png"), img("https://x.com/other.png")]),
    ]
    const images = collectSessionImages(messages)
    expect(images.map((i) => i.url)).toEqual([
      "https://x.com/same.png",
      "https://x.com/other.png",
    ])
  })

  it("skips non-image refs, empty target_ids and messages without references", () => {
    const messages = [
      msg("m1", "human", [
        { type: "file", target_id: "/tmp/a.md", target_name: "a.md" },
        { type: "video", target_id: "https://x.com/v.mp4", target_name: "v" },
      ]),
      msg("m2", "ai", [img(""), img("https://x.com/keep.png")]),
      msg("m3", "ai", undefined),
    ]
    const images = collectSessionImages(messages)
    expect(images.map((i) => i.url)).toEqual(["https://x.com/keep.png"])
  })

  it("falls back to target_id for name and returns empty for no images", () => {
    const empty = collectSessionImages([msg("m1", "human", undefined)])
    expect(empty).toEqual([])

    const one = collectSessionImages([
      msg("m2", "ai", [{ type: "image", target_id: "https://x.com/n.png" }]),
    ])
    expect(one[0].name).toBe("https://x.com/n.png")
  })
})
