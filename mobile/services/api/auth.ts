// 认证 API

import { api } from './client';
import { MEMBER_API } from '@/constants/api';
import {
  ApiResponse,
  LoginResponse,
  RegisterConfig,
  CaptchaConfig,
  CaptchaResponse,
  MobileCodeResponse,
  UserInfo,
  MobileLoginRequest,
  AccountLoginRequest,
} from '@/types';

export const authApi = {
  // 获取注册配置
  getRegisterConfig: async (): Promise<RegisterConfig> => {
    const response = await api.get<ApiResponse<RegisterConfig>>(
      MEMBER_API.REGISTER_CONFIG
    );
    return response.data;
  },

  // 获取验证码配置
  getCaptchaConfig: async (): Promise<CaptchaConfig> => {
    const response = await api.get<ApiResponse<CaptchaConfig>>(
      MEMBER_API.CAPTCHA_CONFIG
    );
    return response.data;
  },

  // 获取图形验证码
  getCaptcha: async (captchaId?: string): Promise<CaptchaResponse> => {
    const response = await api.get<ApiResponse<CaptchaResponse>>(
      MEMBER_API.CAPTCHA_IMAGE,
      {
        params: { captcha_id: captchaId },
      }
    );
    return response.data;
  },

  // 发送手机验证码
  sendMobileCode: async (
    mobile: string,
    captchaCode?: string,
    captchaId?: string
  ): Promise<MobileCodeResponse> => {
    const response = await api.post<ApiResponse<MobileCodeResponse>>(
      MEMBER_API.SEND_MOBILE_CODE,
      {
        mobile,
        captcha_code: captchaCode,
        captcha_id: captchaId,
      }
    );
    return response.data;
  },

  // 手机号登录
  loginWithMobile: async (data: MobileLoginRequest): Promise<LoginResponse> => {
    const response = await api.post<ApiResponse<LoginResponse>>(
      MEMBER_API.LOGIN_MOBILE,
      data
    );
    return response.data;
  },

  // 账号密码登录
  loginWithAccount: async (data: AccountLoginRequest): Promise<LoginResponse> => {
    const response = await api.post<ApiResponse<LoginResponse>>(
      MEMBER_API.LOGIN_ACCOUNT,
      data
    );
    return response.data;
  },

  // 获取用户信息
  getMemberInfo: async (): Promise<UserInfo> => {
    const response = await api.get<ApiResponse<UserInfo>>(
      MEMBER_API.MEMBER_INFO
    );
    return response.data;
  },

  // 修改密码
  changePassword: async (oldPassword: string, newPassword: string): Promise<void> => {
    await api.post(MEMBER_API.CHANGE_PASSWORD, {
      old_password: oldPassword,
      new_password: newPassword,
    });
  },

  // 发送短信验证码（用于绑定手机）
  sendSmsCode: async (mobile: string): Promise<void> => {
    await api.post(MEMBER_API.SEND_SMS_CODE, { mobile });
  },

  // 绑定手机号
  bindMobile: async (mobile: string, code: string): Promise<void> => {
    await api.post(MEMBER_API.BIND_MOBILE, { mobile, code });
  },
};
