// 认证 API

import { api, apiRaw } from './client';
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
      `/member/api/register/config`
    );
    return response.data;
  },

  // 获取验证码配置
  getCaptchaConfig: async (): Promise<CaptchaConfig> => {
    const response = await api.get<ApiResponse<CaptchaConfig>>(
      `/member/api/config/getCaptchaConfig`
    );
    return response.data;
  },

  // 获取图形验证码（直接 axios 调用，处理 blob 响应）
  getCaptcha: async (captchaId?: string): Promise<CaptchaResponse> => {
    const response = await apiRaw.get('/member/api/captcha/captcha', {
      params: { captcha_id: captchaId },
      responseType: 'arraybuffer',
    });

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
      `/member/api/login/mobileCode`,
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
      `/member/api/login/mobile`,
      data
    );
    return response.data;
  },

  // 账号密码登录
  loginWithAccount: async (data: AccountLoginRequest): Promise<LoginResponse> => {
    const response = await api.post<ApiResponse<LoginResponse>>(
      `/member/api/login/login`,
      data
    );
    return response.data;
  },

  // 获取用户信息
  getMemberInfo: async (): Promise<UserInfo> => {
    const response = await api.get<ApiResponse<UserInfo>>(
      `/member/api/member/info`
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
    await api.post(`/member/api/register/mobile`, data);
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
    await api.post(`/member/api/register/username`, data);
  },

  // 发送注册验证码
  sendRegisterMobileCode: async (
    mobile: string,
    captchaCode?: string,
    captchaId?: string
  ): Promise<MobileCodeResponse> => {
    const response = await api.post<ApiResponse<MobileCodeResponse>>(
      `/member/api/register/mobileCode`,
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
      `/member/api/findpassword/mobilecode`,
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
    await api.post(`/member/api/findpassword/mobile`, data);
  },

  // ========== 修改密码 ==========

  // 修改密码（参照 mobile_uniapp）
  modifyPassword: async (data: {
    old_password?: string;
    new_password: string;
    code?: string;
    key?: string;
  }): Promise<void> => {
    await api.post(`/member/api/member/modifypassword`, data);
  },

  // ========== 绑定手机号 ==========

  // 发送绑定手机号的短信验证码
  sendBindMobileCode: async (
    mobile: string,
    captchaCode?: string,
    captchaId?: string
  ): Promise<MobileCodeResponse> => {
    const response = await api.post<ApiResponse<MobileCodeResponse>>(
      `/member/api/member/bindmobliecode`,
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
    await api.post(`/member/api/member/modifymobile`, data);
  },

  // ========== 注销账号 ==========

  // 注销账号
  deleteAccount: async (): Promise<void> => {
    await api.post(`/member/api/member/delete`);
  },

  // ========== 头像 ==========

  // 上传头像（Base64）
  uploadHeadimgBase64: async (base64Image: string): Promise<{ pic_path: string }> => {
    const response = await api.post<ApiResponse<{ pic_path: string }>>(
      `/member/api/upload/headimgBase64`,
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
    await api.post(`/member/api/member/modifyheadimg`, { headimg });
  },
};
