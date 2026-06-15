import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { SubscriptionService } from "@/client"
import useCustomToast from "@evoloop/shared/hooks/useCustomToast"
import { handleError } from "@/utils"
import { SubscriptionDetail, SubscriptionPlan, AiQuota, OrderStatus } from "@/types/subscription"

export const useSubscription = () => {
    const queryClient = useQueryClient()
    const { showErrorToast } = useCustomToast()

    // Query: Current Subscription Status & Detail
    const { data: status, isLoading: isLoadingStatus } = useQuery({
        queryKey: ["subscription", "status"],
        queryFn: () => SubscriptionService.getSubscriptionStatus(),
        refetchInterval: 1000 * 60 * 5, // Poll every 5 min (changes are webhook-driven)
        staleTime: 1000 * 60 * 5,
    })

    const { data: detail, isLoading: isLoadingDetail } = useQuery({
        queryKey: ["subscription", "detail"],
        queryFn: () => SubscriptionService.getSubscriptionDetail(),
        enabled: !!status && (status as any).code === 0,
        staleTime: 1000 * 60 * 2, // 2 minutes
    })

    // Query: Available Plans
    const { data: plans, isLoading: isLoadingPlans } = useQuery({
        queryKey: ["subscription", "plans"],
        queryFn: () => SubscriptionService.getSubscriptionPlans(),
        staleTime: 1000 * 60 * 60, // 1 hour
    })

    // Query: AI Quota (统一配额池)
    const { data: quota, isLoading: isLoadingQuota, refetch: refetchQuota } = useQuery({
        queryKey: ["subscription", "quota"],
        queryFn: () => SubscriptionService.getAiQuota(),
        refetchInterval: 1000 * 60 * 2, // Poll every 2 min (matches backend cache TTL)
        staleTime: 1000 * 60 * 2,
    })

    // Mutation: Create Order
    const createOrderMutation = useMutation({
        mutationFn: (levelId: number) =>
            SubscriptionService.createSubscriptionOrder({ requestBody: { level_id: levelId } }),
        onError: handleError.bind(showErrorToast),
    })

    // Mutation: Cancel Subscription
    const cancelSubscriptionMutation = useMutation({
        mutationFn: (data: { type?: string; reason?: string }) =>
            SubscriptionService.cancelSubscription({ cancelType: data.type, reason: data.reason }),
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ["subscription"] })
        },
        onError: handleError.bind(showErrorToast),
    })

    // Query for checking order status (usually called manually or within a specific effect)
    const checkOrderStatus = async (orderId: string): Promise<OrderStatus | null> => {
        try {
            const res = await SubscriptionService.checkSubscriptionOrderStatus({ orderId })
            return (res as any)?.data as OrderStatus
        } catch (e) {
            console.error("Failed to check order status", e)
            return null
        }
    }

    return {
        status: (status as any)?.data,
        detail: (detail as any)?.data as SubscriptionDetail,
        plans: ((plans as any)?.data || []) as SubscriptionPlan[],
        quota: (quota as any)?.data as AiQuota,
        isLoading: isLoadingStatus || isLoadingPlans || isLoadingQuota || isLoadingDetail,
        refetchQuota,
        refetchDetail: () => queryClient.invalidateQueries({ queryKey: ["subscription", "detail"] }),
        createOrderMutation,
        cancelSubscriptionMutation,
        checkOrderStatus
    }
}
