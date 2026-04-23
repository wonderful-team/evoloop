// 订阅/配额状态管理

import { create } from 'zustand';
import { persist, createJSONStorage } from 'zustand/middleware';
import AsyncStorage from '@react-native-async-storage/async-storage';
import { subscriptionApi } from '@/services/api/subscription';
import { isAuthError } from '@/utils/error';

interface QuotaInfo {
  total: number;
  used: number;
  remaining: number;
  reset_time?: string;
}

interface SubscriptionState {
  quotaInfo: QuotaInfo | null;
  isLoading: boolean;
  isQuotaExhausted: boolean;

  // Actions
  checkQuota: () => Promise<void>;
  getQuotaStatus: () => { total: number; used: number; remaining: number };
}

export const useSubscriptionStore = create<SubscriptionState>()(
  persist(
    (set, get) => ({
      quotaInfo: null,
      isLoading: false,
      isQuotaExhausted: false,

      checkQuota: async () => {
        set({ isLoading: true });
        try {
          const result = await subscriptionApi.getQuota();
          set({
            quotaInfo: result,
            isQuotaExhausted: result.remaining <= 0,
          });
        } catch (error) {
          // 认证错误已在 API client 中统一处理，不需要输出错误日志
          if (!isAuthError(error)) {
            console.error('检查配额失败:', error);
          }
        } finally {
          set({ isLoading: false });
        }
      },

      getQuotaStatus: () => {
        const { quotaInfo } = get();
        return {
          total: quotaInfo?.total || 0,
          used: quotaInfo?.used || 0,
          remaining: quotaInfo?.remaining || 0,
        };
      },
    }),
    {
      name: 'subscription-storage',
      storage: createJSONStorage(() => AsyncStorage),
      partialize: (state) => ({
        quotaInfo: state.quotaInfo,
        isQuotaExhausted: state.isQuotaExhausted,
      }),
    }
  )
);
