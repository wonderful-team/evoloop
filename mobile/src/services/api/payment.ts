// 支付 API

import { api } from './client';
import { MEMBER_API } from '@/constants/api';
import {
  ApiResponse,
  PayRequest,
  WechatPayParams,
  PayStatus,
} from '@/types';

export const paymentApi = {
  // 获取支付信息
  getPayInfo: async (outTradeNo: string): Promise<any> => {
    const response = await api.get<ApiResponse<any>>(MEMBER_API.PAY_INFO, {
      params: { out_trade_no: outTradeNo },
    });
    return response.data;
  },

  // 发起支付
  initiatePay: async (data: PayRequest): Promise<WechatPayParams> => {
    const response = await api.post<ApiResponse<WechatPayParams>>(
      MEMBER_API.PAY,
      data
    );
    return response.data;
  },

  // 查询支付状态
  getPayStatus: async (outTradeNo: string): Promise<PayStatus> => {
    const response = await api.get<ApiResponse<PayStatus>>(
      MEMBER_API.PAY_STATUS,
      {
        params: { out_trade_no: outTradeNo },
      }
    );
    return response.data;
  },

  // 轮询支付状态
  pollPayStatus: async (
    outTradeNo: string,
    onSuccess: () => void,
    onTimeout: () => void,
    maxAttempts: number = 60,
    interval: number = 1000
  ): Promise<void> => {
    let attempts = 0;

    const check = async () => {
      try {
        const status = await paymentApi.getPayStatus(outTradeNo);

        if (status.pay_status === 2) {
          // 已支付
          onSuccess();
          return;
        }

        attempts++;
        if (attempts >= maxAttempts) {
          onTimeout();
          return;
        }

        setTimeout(check, interval);
      } catch (error) {
        attempts++;
        if (attempts >= maxAttempts) {
          onTimeout();
          return;
        }
        setTimeout(check, interval);
      }
    };

    check();
  },
};
