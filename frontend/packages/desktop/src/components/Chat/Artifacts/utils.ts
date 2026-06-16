export interface ExtractedPart {
  type: "text" | "artifact"
  artifactType?: string
  data?: any
  content?: string
}

function findMatchingBraceEnd(text: string, startIndex: number): number {
  if (text[startIndex] !== "{") return -1
  let depth = 1
  for (let i = startIndex + 1; i < text.length; i++) {
    const char = text[i]
    if (char === '"') {
      // Skip string literal
      i++
      while (i < text.length) {
        if (text[i] === "\\") {
          i += 2
        } else if (text[i] === '"') {
          break
        } else {
          i++
        }
      }
      continue
    }
    if (char === "{") depth++
    if (char === "}") {
      depth--
      if (depth === 0) return i
    }
  }
  return -1
}

/**
 * Extract artifact JSON blocks from message content.
 * Supports:
 * 1. Whole message being a single artifact JSON (fast path)
 * 2. Artifact JSON embedded within text (mixed content)
 * 3. Artifact JSON inside ```json code blocks
 *
 * Returns an array of text/artifact parts in order.
 */
const CODE_BLOCK_ARTIFACT_TYPES: Record<string, string> = {
  artifact: "html",
}

export function extractArtifactsFromContent(content: string): ExtractedPart[] {
  const trimmed = content.trim()
  if (!trimmed) return [{ type: "text", content: "" }]

  // Fast path: whole message is a single artifact JSON
  if (trimmed.startsWith("{") && trimmed.endsWith("}")) {
    try {
      const obj = JSON.parse(trimmed)
      if (
        obj &&
        typeof obj === "object" &&
        obj.type === "artifact" &&
        obj.artifact_type &&
        obj.data
      ) {
        return [
          {
            type: "artifact",
            artifactType: obj.artifact_type as string,
            data: obj.data,
          },
        ]
      }
    } catch {
      // Not valid JSON or not an artifact, fall through to mixed extraction
    }
  }

  const parts: ExtractedPart[] = []
  let lastIndex = 0

  // First, try to find artifacts inside ```json / ``` code blocks
  const codeBlockRegex = /```[a-zA-Z0-9_-]*\s*\n?([\s\S]*?)```/g
  let cbMatch: RegExpExecArray | null
  const codeBlockArtifacts: Array<{
    start: number
    end: number
    part: ExtractedPart
  }> = []

  while ((cbMatch = codeBlockRegex.exec(trimmed)) !== null) {
    const rawContent = cbMatch[1]
    const jsonStr = rawContent.trim()

    // 1. Try JSON artifact (existing behavior)
    if (jsonStr.startsWith("{") && jsonStr.endsWith("}")) {
      try {
        const obj = JSON.parse(jsonStr)
        if (
          obj &&
          typeof obj === "object" &&
          obj.type === "artifact" &&
          obj.artifact_type &&
          obj.data
        ) {
          codeBlockArtifacts.push({
            start: cbMatch.index,
            end: cbMatch.index + cbMatch[0].length,
            part: {
              type: "artifact",
              artifactType: obj.artifact_type as string,
              data: obj.data,
            },
          })
          continue
        }
      } catch {
        // not a valid artifact JSON
      }
    }

    // 2. Try non-JSON artifact code blocks (e.g. ```artifact\n<html>...)
    const firstLineEnd = rawContent.indexOf("\n")
    if (firstLineEnd !== -1) {
      const lang = rawContent.slice(0, firstLineEnd).trim().toLowerCase()
      const artifactType = CODE_BLOCK_ARTIFACT_TYPES[lang]
      if (artifactType) {
        const blockContent = rawContent.slice(firstLineEnd + 1).trim()
        codeBlockArtifacts.push({
          start: cbMatch.index,
          end: cbMatch.index + cbMatch[0].length,
          part: {
            type: "artifact",
            artifactType,
            data: { html: blockContent },
          },
        })
      }
    }
  }

  // If code block artifacts found, use them
  if (codeBlockArtifacts.length > 0) {
    for (const ca of codeBlockArtifacts) {
      if (ca.start > lastIndex) {
        const text = trimmed.slice(lastIndex, ca.start).trim()
        if (text) parts.push({ type: "text", content: text })
      }
      parts.push(ca.part)
      lastIndex = ca.end
    }
    if (lastIndex < trimmed.length) {
      const text = trimmed.slice(lastIndex).trim()
      if (text) parts.push({ type: "text", content: text })
    }
    return parts
  }

  // Inline JSON extraction: scan for all top-level { ... } objects
  // and check if they are artifacts
  let i = 0
  while (i < trimmed.length) {
    if (trimmed[i] === "{") {
      const end = findMatchingBraceEnd(trimmed, i)
      if (end !== -1) {
        const jsonStr = trimmed.slice(i, end + 1)
        try {
          const obj = JSON.parse(jsonStr)
          if (
            obj &&
            typeof obj === "object" &&
            obj.type === "artifact" &&
            obj.artifact_type &&
            obj.data
          ) {
            if (i > lastIndex) {
              const text = trimmed.slice(lastIndex, i).trim()
              if (text) parts.push({ type: "text", content: text })
            }
            parts.push({
              type: "artifact",
              artifactType: obj.artifact_type as string,
              data: obj.data,
            })
            lastIndex = end + 1
            i = end + 1
            continue
          }
        } catch {
          // Not valid artifact JSON
        }
      }
    }
    i++
  }

  if (lastIndex < trimmed.length) {
    const text = trimmed.slice(lastIndex).trim()
    if (text) parts.push({ type: "text", content: text })
  }

  return parts.length > 0 ? parts : [{ type: "text", content: trimmed }]
}
