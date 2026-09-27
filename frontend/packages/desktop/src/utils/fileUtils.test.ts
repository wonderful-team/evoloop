import {describe, expect, it} from "vitest"

import {cleanFileUrl, getFileName, getRawFileUrl, isAbsolutePath, resolveReferencePreview,} from "./fileUtils"

describe("isAbsolutePath", () => {
  it("detects posix absolute paths", () => {
    expect(isAbsolutePath("/etc/hosts")).toBe(true)
    expect(isAbsolutePath("/Users/foo/bar")).toBe(true)
  })

  it("detects tildes and windows drive paths", () => {
    expect(isAbsolutePath("~/notes.txt")).toBe(true)
    expect(isAbsolutePath("C:\\Users\\foo\\a.txt")).toBe(true)
    expect(isAbsolutePath("D:/data/x.log")).toBe(true)
  })

  it("rejects relative paths", () => {
    expect(isAbsolutePath("notes.txt")).toBe(false)
    expect(isAbsolutePath("./notes.txt")).toBe(false)
    expect(isAbsolutePath("../notes.txt")).toBe(false)
    expect(isAbsolutePath("uploads/img.png")).toBe(false)
  })
})

describe("getFileName", () => {
  it("returns the trailing segment", () => {
    expect(getFileName("/a/b/c.txt")).toBe("c.txt")
    expect(getFileName("c.txt")).toBe("c.txt")
  })

  it("trailing slash returns the whole path (accepted quirk)", () => {
    // path.split("/").pop() is "" which is falsy -> returns the original path.
    expect(getFileName("/a/b/")).toBe("/a/b/")
  })
})

describe("cleanFileUrl", () => {
  it("strips the file:// scheme", () => {
    expect(cleanFileUrl("file:///Users/foo/a.txt")).toBe("/Users/foo/a.txt")
  })

  it("leaves non-file URLs untouched", () => {
    expect(cleanFileUrl("http://x/y.png")).toBe("http://x/y.png")
  })
})

describe("getRawFileUrl", () => {
  it("builds an abs-path url for absolute/upload paths", () => {
    expect(getRawFileUrl("/etc/passwd", 3, "http://api")).toBe(
      "http://api/api/v1/files/raw?path=%2Fetc%2Fpasswd",
    )
    expect(getRawFileUrl("uploads/x.png")).toBe(
      "/api/v1/files/raw?path=uploads%2Fx.png",
    )
  })

  it("builds a project-scoped url otherwise", () => {
    const url = getRawFileUrl("notes.md", 5, "http://api")
    expect(url).toContain("project_id=5")
    expect(url).toContain("path=notes.md")
  })

  it("projects missing id default to 0", () => {
    expect(getRawFileUrl("notes.md")).toContain("project_id=0")
  })
})

describe("getRawFileUrl", () => {
  it("passes public http(s) URLs through untouched", () => {
    const url = "https://evoloop.cn/upload/chat_img/20260914/x.png"
    expect(getRawFileUrl(url, 0)).toBe(url)
  })

  it("passes same-origin /api/ links through with apiBase prefix (legacy refs)", () => {
    expect(
      getRawFileUrl(
        "/api/v1/files/raw?project_id=0&path=uploads/ref.jpg",
        120,
        "http://127.0.0.1:20160",
      ),
    ).toBe("http://127.0.0.1:20160/api/v1/files/raw?project_id=0&path=uploads/ref.jpg")
  })
})

describe("resolveReferencePreview", () => {
  const base = { type: "image" as const, target_name: "generated image" }

  it("prefers http target_id for image refs (cloud canonical URL)", () => {
    const preview = resolveReferencePreview({
      ...base,
      target_id: "https://evoloop.cn/upload/chat_img/x.png",
      meta_data: { source_path: "https://old.example/legacy.png" },
    })
    expect(preview?.path).toBe("https://evoloop.cn/upload/chat_img/x.png")
  })

  it("falls back to source_path for image refs without http target_id", () => {
    const preview = resolveReferencePreview({
      ...base,
      target_id: "uploads/x.png",
      meta_data: { source_path: "/abs/local/x.png" },
    })
    expect(preview?.path).toBe("/abs/local/x.png")
  })

  it("resolves legacy human image refs (/api/ target_id) without nesting", () => {
    const preview = resolveReferencePreview({
      type: "image",
      target_id: "/api/v1/files/raw?project_id=0&path=uploads/ref_05_786.jpg",
      target_name: "ref_05_786.jpg",
      meta_data: { filename: "ref_05_786.jpg" },
    })
    expect(preview?.path).toBe(
      "/api/v1/files/raw?project_id=0&path=uploads/ref_05_786.jpg",
    )
    expect(preview?.name).toBe("ref_05_786.jpg")
  })

  it("keeps source_path priority for file refs (local text preview)", () => {
    const preview = resolveReferencePreview({
      type: "file",
      target_id: "https://evoloop.cn/api-link",
      target_name: "a.md",
      meta_data: { source_path: "/workspace/a.md" },
    })
    expect(preview?.path).toBe("/workspace/a.md")
  })
})
