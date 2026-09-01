import type { MacroStepEntry } from "@/components/Learning/macroRun"

export interface AgentState {
  // Activity State
  status:
    | "idle"
    | "running"
    | "error"
    | "stopped"
    | "interrupted"
    | "summarizing"
    | "indexing"
    | "quota_exhausted"
    | "unauthorized"
    | "unknown"

  finalOutcome: string | null
  activeMemories: Array<{ id: string; name: string }>
  artifacts: Array<{
    id: number
    name: string
    type: string
    status: string
    path?: string
  }>
  humanRequest: any | null
  quotaExhaustedInfo: {
    title: string
    message: string
    hint: string
    actionText: string
  } | null
  agentState: {
    mode: string
    task_name: string
    task_status: string
    details?: any
    activeSkills?: Array<{
      id: number
      name: string
      description: string
    }> | null
  } | null

  // --- Live Buffer (For Right Panel) ---
  streamingThinking: string
  _thinkingBuffer: string
  _flushTimeout: ReturnType<typeof setTimeout> | null
  streamingSteps: any[]

  // --- Live subagent panel (started / completed / failed / cancelled) ---
  subagents: Array<{
    subagent_id: string
    subagent_thread_id: string
    instruction: string
    status: string
    result?: string
    error?: string | null
  }>

  // --- Live A2A delegation panel (started / completed / failed / timeout / cancelled) ---
  a2aDelegations: Array<{
    task_id: string
    target_device_key: string
    target_device_name?: string
    instruction: string
    status: string
    result?: string
    error?: string | null
  }>
  /** Selected A2A delegation to show in the main chat-area detail tab (task_id) */
  activeA2ADetail: string | null

  // --- Macro step feed (macro_thought from MacroEngine, current thread) ---
  macroSteps: MacroStepEntry[]

  isConnected: boolean
  connectionStatus: string

  // Internal Handlers for WebSocket events
  _setConnectionStatus: (connected: boolean, status: string) => void
  _appendThinking: (text: string) => void
  _setActivitySnapshot: (snapshot: any) => void
  _appendMacroStep: (payload: unknown) => void
  _addArtifact: (artifact: any) => void
  _updateStatus: (status: any) => void
  _setHumanRequest: (request: any) => void
  _setQuotaExhausted: (info: {
    title: string
    message: string
    hint: string
    actionText: string
  }) => void
  _setLLMAuthError: (ev: any) => void
  _updateProgress: (ev: any) => void
  _setAgentState: (ev: any) => void
  _handleRunStart: (ev: any) => void
  _handleRunEnd: (ev: any) => void
  _handleSessionCompleted: (ev: any) => void
  _handleSubagentLifecycle: (ev: any) => void
  _handleA2ALifecycle: (ev: any) => void
  /** Selected subagent to show in the main chat-area detail tab (thread_id) */
  activeSubagentDetail: string | null
  _openSubagentDetail: (threadId: string) => void
  _closeSubagentDetail: () => void
  _openA2ADetail: (taskId: string) => void
  _closeA2ADetail: () => void
  _setError: (error: string) => void
  clearContent: () => void

  // Actions
  stopAgent: () => Promise<void>
  resumeAgent: (
    userInput?: string,
    grantMode?: "once" | "always" | "default",
  ) => Promise<void>
  cancelHumanRequest: (reason?: string) => Promise<void>
}
