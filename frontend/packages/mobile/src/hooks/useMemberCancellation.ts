/**
 * Mobile-specific Member Cancellation Hook
 * Uses the mobile client API
 */
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { MemberService } from "../client"
import useCustomToast from "./useCustomToast"

export const useMemberCancellation = () => {
  const { showSuccessToast, showErrorToast } = useCustomToast()
  const queryClient = useQueryClient()

  const { data: info, isLoading } = useQuery({
    queryKey: ["memberCancellation"],
    queryFn: async () => {
      try {
        const res = await MemberService.getCancellationInfo()
        return res.data
      } catch {
        return null
      }
    },
  })

  const applyMutation = useMutation({
    mutationFn: () => MemberService.applyCancellation(),
    onSuccess: (res: any) => {
      if (res?.code >= 0) {
        showSuccessToast("Cancellation applied successfully.")
        queryClient.invalidateQueries({ queryKey: ["memberCancellation"] })
      } else {
        showErrorToast(res?.message || "Failed to apply.")
      }
    },
    onError: (err: any) => {
      showErrorToast(err.message || "Error applying cancellation.")
    },
  })

  const cancelMutation = useMutation({
    mutationFn: () => MemberService.cancelCancellation(),
    onSuccess: (res: any) => {
      if (res?.code >= 0) {
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
