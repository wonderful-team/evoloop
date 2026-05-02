import { ChatState } from "./types"
import type { Message } from "@/components/Chat/ChatMessageItem"

/**
 * Commits current streaming thinking buffer to the last AI message
 */
export function commitThinkingBuffer(state: ChatState) {
    if (!state.streamingThinking) return {}
    
    const newMsgs = [...state.messages]
    const lastAi = [...newMsgs].reverse().find(m => m.role === "ai")
    if (lastAi) {
        lastAi.thinking = (lastAi.thinking || "") + state.streamingThinking
    }
    
    return { 
        messages: newMsgs, 
        streamingThinking: "" 
    }
}

/**
 * Normalizes and prepares a raw message object for the store
 */
export function normalizeMessage(rawMsg: any): any {
    // Mapping roles to support flat architecture (human, ai, tool)
    let normalizedRole: "human" | "ai" | "tool" = "ai"
    if (rawMsg.role === "human" || rawMsg.role === "user") normalizedRole = "human"
    if (rawMsg.role === "tool") normalizedRole = "tool"

    return {
        id: rawMsg.id,
        role: normalizedRole,
        originalRole: rawMsg.role,
        content: rawMsg.content || "",
        thinking: rawMsg.thinking,
        timestamp: rawMsg.created_at || new Date().toISOString(),
        steps: rawMsg.steps || [],
        references: rawMsg.references || [],
        changeset_count: rawMsg.changeset_count || 0,
        category: rawMsg.category,
        status: rawMsg.status,
        node_source: rawMsg.node_source,
        run_id: rawMsg.run_id,
        meta_data: rawMsg.meta_data || {},
    }
}

/**
 * Parses a system message for HITL requests
 */
export function tryParseHumanRequest(rawMsg: any): any | null {
    if (rawMsg.category === "HITL_REQUEST" || rawMsg.category === "INTERRUPT") {
        try {
            let parsed = typeof rawMsg.content === "string" ? JSON.parse(rawMsg.content) : rawMsg.content
            if (parsed && typeof parsed.type === "string" && typeof parsed.prompt === "string") {
                return { ...parsed, status: rawMsg.status }
            }
        } catch (e) {
            console.error("[ChatStore] Failed to parse HITL_REQUEST content:", e)
        }
    }

    if (rawMsg.role === "system" && rawMsg.content) {
        try {
            let parsed = typeof rawMsg.content === "string" ? JSON.parse(rawMsg.content) : rawMsg.content
            if (parsed && typeof parsed.type === "string" && typeof parsed.prompt === "string") {
                return { ...parsed, status: rawMsg.status }
            }
        } catch { /* not JSON */ }
    }
    return null
}
