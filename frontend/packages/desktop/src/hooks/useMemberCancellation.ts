import useCustomToast from "@evoloop/shared/hooks/useCustomToast"
import {useMutation, useQuery, useQueryClient} from "@tanstack/react-query"
import {useTranslation} from "react-i18next"
import {MemberService} from "@/client/sdk.gen"

type Platform = "mobile" | "desktop"

export const useMemberCancellation = (platform: Platform = "desktop") => {
  const { t } = useTranslation()
  const { showSuccessToast, showErrorToast } = useCustomToast()
  const queryClient = useQueryClient()

  // Select API provider based on platform
  // Unified API (Mobile & Desktop use the same generated client)
  const api = {
    getInfo: MemberService.getCancellationInfo,
    apply: MemberService.applyCancellation,
    cancel: MemberService.cancelCancellation,
  }

  const { data: info, isLoading } = useQuery({
    queryKey: ["memberCancellation", platform],
    queryFn: api.getInfo,
    // Don't refetch too often, maybe on mount
  })

  const applyMutation = useMutation({
    mutationFn: api.apply,
    onSuccess: (res: any) => {
      if (res?.code >= 0 || res?.success) {
        showSuccessToast(t("memberCancellation.applySuccess"))
        queryClient.invalidateQueries({ queryKey: ["memberCancellation"] })
        // Force logout might be needed depending on business logic,
        // but usually cancellation takes time (audit).
      } else {
        showErrorToast(res?.message || t("memberCancellation.applyFailed"))
      }
    },
    onError: (err: any) => {
      showErrorToast(err.message || t("memberCancellation.applyError"))
    },
  })

  const cancelMutation = useMutation({
    mutationFn: api.cancel,
    onSuccess: (res: any) => {
      if (res?.code >= 0 || res?.success) {
        showSuccessToast(t("memberCancellation.withdrawSuccess"))
        queryClient.invalidateQueries({ queryKey: ["memberCancellation"] })
      } else {
        showErrorToast(res?.message || t("memberCancellation.withdrawFailed"))
      }
    },
    onError: (err: any) => {
      showErrorToast(err.message || t("memberCancellation.withdrawError"))
    },
  })

  return {
    info,
    isLoading,
    apply: applyMutation.mutate,
    cancel: cancelMutation.mutate,
    isApplying: applyMutation.isPending,
    isCanceling: cancelMutation.isPending,
  }
}
