// 认证 API

import axios from 'axios';
import { api, API_CONFIG } from './client';
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

  // 获取图形验证码（直接 axios 调用，处理 blob 响应）
  getCaptcha: async (captchaId?: string): Promise<CaptchaResponse> => {
    const response = await axios.get(
      `${API_CONFIG.baseURL}${MEMBER_API.CAPTCHA_IMAGE}`,
      {
        params: { captcha_id: captchaId },
        responseType: 'arraybuffer',
      }
    );

    // 从响应头获取 captcha_id
    const captchaIdFromHeader = response.headers['x-captcha-id'] || response.headers['X-Captcha-Id'];
    // 将二进制数据转为 base64 (React Native 兼容方式)
    const bytes = new Uint8Array(response.data);
    let binary = '';
    for (let i = 0; i < bytes.byteLength; i++) {
      binary += String.fromCharCode(bytes[i]);
    }
    const base64 = btoa(binary);
    const img = `data:image/png;base64,${base64}`;

    return {
      id: captchaIdFromHeader || captchaId || '',
      img,
    };
  },

  // 发送手机验证码（登录用）
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

  // ========== 注册 ==========

  // 手机号注册
  registerWithMobile: async (data: {
    mobile: string;
    key: string;
    code: string;
    password?: string;
    captcha_id?: string;
    captcha_code?: string;
    source_member?: string;
    nickname?: string;
    headimg?: string;
  }): Promise<void> => {
    await api.post(MEMBER_API.REGISTER_MOBILE, data);
  },

  // 用户名注册
  registerWithUsername: async (data: {
    username: string;
    password: string;
    captcha_id?: string;
    captcha_code?: string;
    source_member?: string;
    nickname?: string;
    headimg?: string;
  }): Promise<void> => {
    await api.post(MEMBER_API.REGISTER_USERNAME, data);
  },

  // 发送注册验证码
  sendRegisterMobileCode: async (
    mobile: string,
    captchaCode?: string,
    captchaId?: string
  ): Promise<MobileCodeResponse> => {
    const response = await api.post<ApiResponse<MobileCodeResponse>>(
      MEMBER_API.REGISTER_MOBILE_CODE,
      {
        mobile,
        captcha_code: captchaCode,
        captcha_id: captchaId,
      }
    );
    return response.data;
  },

  // ========== 找回密码 ==========

  // 发送找回密码验证码
  sendFindPasswordCode: async (
    mobile: string,
    captchaCode: string,
    captchaId: string
  ): Promise<MobileCodeResponse> => {
    const response = await api.post<ApiResponse<MobileCodeResponse>>(
      MEMBER_API.FIND_PASSWORD_MOBILE_CODE,
      {
        mobile,
        captcha_code: captchaCode,
        captcha_id: captchaId,
      }
    );
    return response.data;
  },

  // 找回密码（重置）
  resetPassword: async (data: {
    mobile: string;
    key: string;
    code: string;
    password: string;
  }): Promise<void> => {
    await api.post(MEMBER_API.FIND_PASSWORD_MOBILE, data);
  },

  // ========== 修改密码 ==========

  // 修改密码（参照 mobile_uniapp）
  modifyPassword: async (data: {
    old_password?: string;
    new_password: string;
    code?: string;
    key?: string;
  }): Promise<void> => {
    await api.post(MEMBER_API.MODIFY_PASSWORD, data);
  },

  // ========== 绑定手机号 ==========

  // 发送绑定手机号的短信验证码
  sendBindMobileCode: async (
    mobile: string,
    captchaCode?: string,
    captchaId?: string
  ): Promise<MobileCodeResponse> => {
    const response = await api.post<ApiResponse<MobileCodeResponse>>(
      MEMBER_API.BIND_MOBILE_CODE,
      {
        mobile,
        captcha_code: captchaCode,
        captcha_id: captchaId,
      }
    );
    return response.data;
  },

  // 绑定手机号
  modifyMobile: async (data: {
    mobile: string;
    captcha_id?: string;
    captcha_code?: string;
    code: string;
    key: string;
  }): Promise<void> => {
    await api.post(MEMBER_API.MODIFY_MOBILE, data);
  },

  // ========== 注销账号 ==========

  // 注销账号
  deleteAccount: async (): Promise<void> => {
    await api.post(MEMBER_API.DELETE_ACCOUNT);
  },

  // ========== 头像 ==========

  // 上传头像（Base64）
  uploadHeadimgBase64: async (base64Image: string): Promise<{ pic_path: string }> => {
    const response = await api.post<ApiResponse<{ pic_path: string }>>(
      MEMBER_API.UPLOAD_HEADIMG_BASE64,
      {
        app_type: 'app',
        app_type_name: 'app',
        images: base64Image,
      }
    );
    return response.data;
  },

  // 修改头像
  modifyHeadimg: async (headimg: string): Promise<void> => {
    await api.post(MEMBER_API.MODIFY_HEADIMG, { headimg });
  },
};
