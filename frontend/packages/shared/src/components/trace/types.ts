export type TraceNodeKind =
  | "instruction"
  | "think"
  | "tool"
  | "artifact"
  | "error"
  | "hitl"
  | "system"

export type TraceNodeStatus =
  | "pending"
  | "running"
  | "streaming"
  | "success"
  | "completed"
  | "failed"
  | "waiting_human"

export interface ToolCallTraceData {
  toolName: string
  displayName?: string
  input?: Record<string, unknown>
  output?: unknown
  status?: TraceNodeStatus
  changesetCount?: number
  error?: string
}

export interface ThinkingTraceData {
  thinking: string
  isStreaming?: boolean
  duration?: string
}

export interface TraceNodeItem {
  id: string | number
  kind: TraceNodeKind
  title?: string
  content?: string
  status?: TraceNodeStatus
  toolData?: ToolCallTraceData
  thinkingData?: ThinkingTraceData
  timestamp?: string | number
  raw?: unknown
}
