import { useMutation, useQueryClient } from "@tanstack/react-query"
import { useTranslation } from "react-i18next"
import { toast } from "sonner"
import { AgentService, ConversationsService } from "@/client"
import { ChatConnection } from "@/lib/ChatConnection"
import { useChangesetStore } from "@/stores/changesetStore"
import { useChatStore } from "@/stores/chatStore"

export function useChatMutations({
  setIsRewindDialogOpen,
  setRewindContent,
  chatInputRef,
}: {
  setIsRewindDialogOpen: (open: boolean) => void
  setRewindContent: (content: string) => void
  chatInputRef: React.RefObject<any>
}) {
  const { t } = useTranslation()
  const _queryClient = useQueryClient()
  const activeThreadId = useChatStore((s) => s.threadId)
  const projectId = useChatStore((s) => s.projectId)
  const selectedModel = useChatStore((s) => s.selectedModel)
  const setThread = useChatStore((s) => s.setThread)

  const rewindMutation = useMutation({
    mutationFn: ({
      revertFiles,
      messageId,
      content,
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
    onSuccess: (data: any) => {
      const filesMsg =
        data.files_reverted && data.files_reverted > 0
          ? t("chat.interface.filesRevertedMessage", {
              count: data.files_reverted,
            })
          : ""
      toast.success(`${t("chat.interface.retrying")}${filesMsg}`)

      // Reload store to reflect rolled back state and new streaming status
      if (activeThreadId && projectId) {
        setThread(activeThreadId, projectId)
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
