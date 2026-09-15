import { useMutation } from "@tanstack/react-query"
import { useTranslation } from "react-i18next"
import { toast } from "sonner"
import { AgentService, ConversationsService } from "@/client"
import { ChatConnection } from "@/lib/ChatConnection"
import { useChangesetStore } from "@/stores/changesetStore"
import { useChatStore } from "@/stores/chatStore"
import { useHostContextStore } from "@/stores/hostContextStore"

export function useChatMutations({
  setIsRewindDialogOpen,
  chatInputRef,
}: {
  setIsRewindDialogOpen: (open: boolean) => void
  chatInputRef: React.RefObject<any>
}) {
  const { t } = useTranslation()
  const activeThreadId = useChatStore((s) => s.threadId)
  const projectId = useChatStore((s) => s.projectId)
  const selectedModel = useChatStore((s) => s.selectedModel)
  const setThread = useChatStore((s) => s.setThread)

  const rewindMutation = useMutation({
    mutationFn: ({
      revertFiles,
      messageId,
      content: _content,
    }: {
      revertFiles: boolean
      messageId?: string
      content?: string
    }) =>
      ConversationsService.rewindConversation({
        threadId: activeThreadId!,
        requestBody: {
          revert_files: revertFiles,
          message_id: messageId,
        },
      } as any),
    onMutate: ({ messageId }) => {
      const snapshot = useChatStore
        .getState()
        .optimisticTruncate(messageId || "", true)
      return { snapshot }
    },
    onSuccess: (data: any, _variables: any) => {
      if (activeThreadId) {
        useChangesetStore.getState().fetchChangeset(activeThreadId)
      }
      const filesMsg =
        data.files_reverted && data.files_reverted > 0
          ? t("chat.interface.filesRevertedMessage", {
              count: data.files_reverted,
            })
          : ""

      toast.success(`${t("chat.interface.rewindSuccess")}${filesMsg}`)
      setIsRewindDialogOpen(false)

      if (_variables.content && chatInputRef.current) {
        chatInputRef.current.setInput(_variables.content)
      }
    },
    onError: (_error, _variables, context: any) => {
      if (context?.snapshot) {
        useChatStore.getState().restoreSnapshot(context.snapshot)
      }
      toast.error(t("chat.errors.rewindFailed"))
    },
  })

  const retryMutation = useMutation({
    mutationFn: async ({
      revertFiles,
      messageId,
    }: {
      revertFiles: boolean
      messageId?: string
    }) => {
      if (activeThreadId) {
        ChatConnection.getInstance().connect(activeThreadId)
      }
      return AgentService.retryChat({
        requestBody: {
          thread_id: activeThreadId,
          message: "",
          project_id: projectId,
          revert_files: revertFiles,
          message_id: messageId,
          model: selectedModel,
          // 重试时附带当前宿主上下文（后端还会从被重试消息的 meta_data 兜底恢复）
          host_context: (() => {
            const hc = useHostContextStore.getState().context
            if (!hc) return undefined
            return {
              route: hc.route,
              page_name: hc.pageName,
              entity: hc.entity,
              domain: hc.domain ?? undefined,
              ts: hc.ts,
            }
          })(),
        },
      } as any)
    },
    onMutate: ({ messageId }) => {
      const snapshot = useChatStore
        .getState()
        .optimisticTruncate(messageId || "")
      window.dispatchEvent(new CustomEvent("chat-scroll-to-bottom"))
      return { snapshot }
    },
    onSuccess: async (data: any) => {
      const filesMsg =
        data.files_reverted && data.files_reverted > 0
          ? t("chat.interface.filesRevertedMessage", {
              count: data.files_reverted,
            })
          : ""
      toast.success(`${t("chat.interface.retrying")}${filesMsg}`)

      // Reload store to reflect rolled back state and new streaming status.
      // setThread replaces the message list and reconnects SSE; wait for it to
      // settle before scrolling to the bottom — otherwise the first streamed
      // messages arrive while the viewport is no longer at the bottom and the
      // list stops following (scrollbar gets pushed up by incoming SSE).
      if (activeThreadId && projectId) {
        await setThread(activeThreadId, projectId)
        window.dispatchEvent(new CustomEvent("chat-scroll-to-bottom"))
      }
      setIsRewindDialogOpen(false)
    },
    onError: (_error, _variables, context: any) => {
      if (context?.snapshot) {
        useChatStore.getState().restoreSnapshot(context.snapshot)
      }
      toast.error(t("chat.interface.retryFailed"))
    },
  })

  return { rewindMutation, retryMutation }
}
