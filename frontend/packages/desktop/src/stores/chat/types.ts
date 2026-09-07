import type { Message } from "@/components/Chat/ChatMessageItem"

export interface ActivitySnapshot {
  status: string
  main_goal: string
  updated_at: number
  running_tools_count: number
  artifacts: any[]
  agent_state: any
  active_memories: any[]
  human_request: any | null
  final_outcome: string
}

export interface ActiveTaskInfo {
  task_id: string
  task_type: string
  title: string
  status: string
  created_at: string
  output: string
  metadata: Record<string, any>
}

export interface ChatState {
  // --- Data ---
  threadId: string | null
  projectId: number | null
  skillIds: number[]
  sessionGoal: string | null
  messages: Message[]

  // AI 创作 deep link 回传元数据（临时，发送后即清空）
  pendingCreateTask: {
    taskId: string
    secret: string
    callbackUrl: string
  } | null

  // Pagination State
  hasMoreHistory: boolean
  isLoadingHistory: boolean
  firstMessageId: number | string | null
  totalMessageCount: number | null

  // Model Selection
  selectedModel: string | null

  // Throttling Logic
  _streamBuffer: string
  _thinkingBuffer: string
  _flushTimeout: any

  // --- Terminal Mode State ---
  isTerminalMode: boolean
  /** Accumulated raw character stream from all PTY output for the current thread */
  terminalHistoryBuffer: string
  /** Running background tasks indexed by task_id */
  activeTasks: Record<string, ActiveTaskInfo>

  // --- Actions ---
  setThread: (
    threadId: string | null,
    projectId: number | null,
    skillIds?: number[],
  ) => Promise<void>
  setPendingCreateTask: (
    data: { taskId: string; secret: string; callbackUrl: string } | null,
  ) => void
  fetchHistory: (threadId: string) => Promise<void>
  fetchActivity: (threadId: string) => Promise<void>
  loadMoreHistory: () => Promise<void>
  sendMessage: (
    content: string,
    pickedFiles?: any[],
    skillIds?: number[],
  ) => Promise<void>
  clearContent: () => void
  setSelectedModel: (model: string | null) => void
  rewindToMessage: (messageId: string) => Promise<void>
  optimisticTruncate: (
    messageId: string | number,
    removeHuman?: boolean,
  ) => Message[]
  restoreSnapshot: (snapshot: Message[]) => void

  // --- Terminal Actions ---
  setTerminalMode: (enabled: boolean) => void
  /** Send a shell command via /terminal/execute (creates a BackgroundTask) */
  sendTerminalCommand: (command: string) => Promise<void>
  /** Cancel a running terminal background task via /terminal/cancel */
  cancelTask: (taskId: string) => Promise<void>
  /** Write raw bytes to PTY — debounced (16 ms) so bursts/pastes send a single POST */
  sendRawTerminalInput: (text: string) => void
  /** Append incremental PTY output to the history buffer */
  appendTerminalOutput: (output: string) => void
  updateActiveTask: (task: ActiveTaskInfo) => void
  removeActiveTask: (taskId: string) => void
  /** Fetch running tasks + log snapshots for reconnect/refresh recovery */
  fetchActiveTasks: (threadId: string) => Promise<void>

  // Internal Handlers
  _appendToken: (tokens: string, messageId?: string) => void
  _appendThinking: (text: string, messageId?: string) => void
  _appendMessage: (msg: any) => void
  _truncateMessages: (index: number) => void
  _handleRunStart: (ev: any) => void
  _finalizeMessages: () => void
  _clearHumanRequest: () => void
  _attachHumanRequestToLastMessage: (req: any) => void
}
