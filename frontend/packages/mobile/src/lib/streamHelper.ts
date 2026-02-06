/**
 * Mobile-specific Stream Helper
 * Uses the mobile client API for cloud chat streaming
 */
import { v4 as uuidv4 } from "uuid"

interface StreamChatParams {
  message: string
  conversation_id?: string // If undefined, new conversation
  attachments?: any[]
}

// Get the cloud API base URL
const getBaseUrl = () => {
  return import.meta.env.VITE_EVOCLOUD_API_URL || "https://mall.imagicbox.cn"
}

/**
 * Helper to stream chat from cloud API
 */
export const streamChat = async (
  params: StreamChatParams,
  onChunk: (chunk: string, meta?: any) => void,
): Promise<void> => {
  let threadId = params.conversation_id
  if (!threadId || threadId === "new") {
    threadId = uuidv4()
  }

  // Get token from localStorage (mobile auth)
  const token = localStorage.getItem("evoloop_token") || localStorage.getItem("access_token") || ""
  const baseUrl = getBaseUrl()

  // Use fetch directly for POST streaming
  const response = await fetch(`${baseUrl}/api/AI/chat`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "X-Requested-With": "XMLHttpRequest",
    },
    body: JSON.stringify({
      message: params.message,
      conversation_id: threadId,
      attachments: params.attachments,
      stream: true,
      token: token, // Pass token in body for convenience if middleware supports it, 
      // or we could add it to headers/params. 
      // AI.php checks $this->params['token'].
    }),
  })

  if (!response.ok) {
    const errorData = await response.json().catch(() => ({}))
    throw {
      status: response.status,
      message: errorData.message || "Failed to start stream",
    }
  }

  if (!response.body) {
    throw new Error("Response body is null")
  }

  const reader = response.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ""

  while (true) {
    const { done, value } = await reader.read()
    if (done) break

    // Decode and add to buffer
    buffer += decoder.decode(value, { stream: true })

    // Process SSE lines
    const lines = buffer.split("\n")
    buffer = lines.pop() || "" // Keep last partial line in buffer

    for (const line of lines) {
      const trimmedLine = line.trim()
      if (!trimmedLine) continue

      if (trimmedLine.startsWith("data:")) {
        const dataStr = trimmedLine.replace(/^data:\s*/, "")
        if (dataStr === "[DONE]") {
          return
        }

        try {
          const data = JSON.parse(dataStr)
          if (data.content) {
            onChunk(data.content, data)
          } else if (typeof data === "string") {
            onChunk(data)
          }
        } catch (e) {
          // Fallback if not JSON
          onChunk(dataStr)
        }
      }
    }
  }
}
