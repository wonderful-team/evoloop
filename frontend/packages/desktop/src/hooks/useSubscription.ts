import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { MemberService } from "@/client"
import useCustomToast from "@evoloop/shared/hooks/useCustomToast"
import { handleError } from "@/utils"

export const useSubscription = () => {
    const queryClient = useQueryClient()
    const { showErrorToast } = useCustomToast()

    // Query: Current Subscription Status & Detail
    const { data: status, isLoading: isLoadingStatus } = useQuery({
        queryKey: ["subscription", "status"],
        queryFn: () => MemberService.getSubscriptionStatus(),
        refetchInterval: 30000, // Poll every 30s
    })

    const { data: detail, isLoading: isLoadingDetail } = useQuery({
        queryKey: ["subscription", "detail"],
        queryFn: () => MemberService.getSubscriptionDetail(),
        enabled: !!status && (status as any).code === 0,
    })

    // Query: Available Plans
    const { data: plans, isLoading: isLoadingPlans } = useQuery({
        queryKey: ["subscription", "plans"],
        queryFn: () => MemberService.getSubscriptionPlans(),
    })

    // Query: AI Quota (统一配额池)
    const { data: quota, isLoading: isLoadingQuota, refetch: refetchQuota } = useQuery({
        queryKey: ["subscription", "quota"],
        queryFn: () => MemberService.getAiQuota(),
        refetchInterval: 60000,
    })

    // Mutation: Create Order
    const createOrderMutation = useMutation({
        mutationFn: (levelId: number) => 
            MemberService.createSubscriptionOrder({ requestBody: { level_id: levelId } }),
        onError: handleError.bind(showErrorToast),
    })

    // Mutation: Cancel Subscription
    const cancelSubscriptionMutation = useMutation({
        mutationFn: (data: { type?: string; reason?: string }) => 
            MemberService.cancelSubscription({ cancelType: data.type, reason: data.reason }),
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ["subscription"] })
        },
        onError: handleError.bind(showErrorToast),
    })

    // Query for checking order status (usually called manually or within a specific effect)
    const checkOrderStatus = async (orderId: string) => {
        try {
            const res = await MemberService.checkSubscriptionOrderStatus({ orderId })
            return (res as any)?.data
        } catch (e) {
            console.error("Failed to check order status", e)
            return null
        }
    }

    return {
        status: (status as any)?.data,
        detail: (detail as any)?.data,
        plans: (plans as any)?.data || [],
        quota: (quota as any)?.data,
        isLoading: isLoadingStatus || isLoadingPlans || isLoadingQuota || isLoadingDetail,
        refetchQuota,
        refetchDetail: () => queryClient.invalidateQueries({ queryKey: ["subscription", "detail"] }),
        createOrderMutation,
        cancelSubscriptionMutation,
        checkOrderStatus
    }
}
