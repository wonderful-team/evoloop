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

  isConnected: boolean
  connectionStatus: string

  // Internal Handlers for WebSocket events
  _setConnectionStatus: (connected: boolean, status: string) => void
  _appendThinking: (text: string) => void
  _setActivitySnapshot: (snapshot: any) => void
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
  _setError: (error: string) => void
  clearContent: () => void

  // Actions
  stopAgent: () => Promise<void>
  resumeAgent: (userInput?: string) => Promise<void>
  cancelHumanRequest: (reason?: string) => Promise<void>
}
