// 订阅 API

import { api } from './client';
import { MEMBER_API } from '@/constants/api';
import {
  ApiResponse,
  SubscriptionPlan,
  SubscriptionStatus,
  MemberBenefits,
  CreateOrderRequest,
  CreateOrderResponse,
  UpgradePriceInfo,
} from '@/types';

export const subscriptionApi = {
  // 获取订阅状态
  getStatus: async (): Promise<SubscriptionStatus> => {
    const response = await api.get<ApiResponse<SubscriptionStatus>>(
      MEMBER_API.SUBSCRIPTION_STATUS
    );
    return response.data;
  },

  // 获取订阅详情
  getDetail: async (): Promise<SubscriptionStatus> => {
    const response = await api.get<ApiResponse<SubscriptionStatus>>(
      MEMBER_API.SUBSCRIPTION_DETAIL
    );
    return response.data;
  },

  // 获取套餐列表
  getPlans: async (): Promise<SubscriptionPlan[]> => {
    const response = await api.get<ApiResponse<SubscriptionPlan[]>>(
      MEMBER_API.SUBSCRIPTION_PLANS
    );
    return response.data;
  },

  // 获取会员权益
  getBenefits: async (): Promise<MemberBenefits> => {
    const response = await api.get<ApiResponse<MemberBenefits>>(
      MEMBER_API.SUBSCRIPTION_BENEFITS
    );
    return response.data;
  },

  // 创建订单
  createOrder: async (data: CreateOrderRequest): Promise<CreateOrderResponse> => {
    const response = await api.post<ApiResponse<CreateOrderResponse>>(
      MEMBER_API.CREATE_ORDER,
      data
    );
    return response.data;
  },

  // 计算升级价格
  calculateUpgradePrice: async (targetLevelId: number): Promise<UpgradePriceInfo> => {
    const response = await api.post<ApiResponse<UpgradePriceInfo>>(
      MEMBER_API.CALCULATE_UPGRADE,
      { target_level_id: targetLevelId }
    );
    return response.data;
  },
};
