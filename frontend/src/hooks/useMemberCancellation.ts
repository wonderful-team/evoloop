import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { MemberService } from "@/client/sdk.gen"
import useCustomToast from "./useCustomToast"

type Platform = "mobile" | "desktop"

export const useMemberCancellation = (platform: Platform = "desktop") => {
  const { showSuccessToast, showErrorToast } = useCustomToast()
  const queryClient = useQueryClient()

  // Select API provider based on platform
  // Unified API (Mobile & Desktop use the same generated client)
  const api = {
    getInfo: MemberService.getCancellationInfo,
    apply: MemberService.applyCancellation,
    cancel: MemberService.cancelCancellationApply,
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
        showSuccessToast("Cancellation applied successfully.")
        queryClient.invalidateQueries({ queryKey: ["memberCancellation"] })
        // Force logout might be needed depending on business logic,
        // but usually cancellation takes time (audit).
      } else {
        showErrorToast(res?.message || "Failed to apply.")
      }
    },
    onError: (err: any) => {
      showErrorToast(err.message || "Error applying cancellation.")
    },
  })

  const cancelMutation = useMutation({
    mutationFn: api.cancel,
    onSuccess: (res: any) => {
      if (res?.code >= 0 || res?.success) {
        showSuccessToast("Cancellation request withdrawn.")
        queryClient.invalidateQueries({ queryKey: ["memberCancellation"] })
      } else {
        showErrorToast(res?.message || "Failed to withdraw.")
      }
    },
    onError: (err: any) => {
      showErrorToast(err.message || "Error withdrawing cancellation.")
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
