import {create} from "zustand"

interface UnreadCompletionsState {
  /** thread_id -> 是否有未读的"会话已完成"提示 */
  unread: Record<string, boolean>
  markUnread: (threadId: string) => void
  clearUnread: (threadId: string) => void
}

export const useUnreadCompletionsStore = create<UnreadCompletionsState>(
  (set) => ({
    unread: {},
    markUnread: (threadId) =>
      set((s) =>
        s.unread[threadId] ? s : { unread: { ...s.unread, [threadId]: true } },
      ),
    clearUnread: (threadId) =>
      set((s) => {
        if (!s.unread[threadId]) return s
        const unread = { ...s.unread }
        delete unread[threadId]
        return { unread }
      }),
  }),
)
