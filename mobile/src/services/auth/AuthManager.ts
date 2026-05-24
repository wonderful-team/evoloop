// 认证管理服务

import { api } from '@/services/api/client';
import { authApi } from '@/services/api/auth';
import i18n from '@/locales';
import {
  ApiResponse,
  LoginResponse,
  RegisterConfig,
  CaptchaConfig,
  CaptchaResponse,
  MobileCodeResponse,
  WechatAuthData,
  UserInfo,
} from '@/types';

// API 响应包装器 - 处理不同的响应结构
function unwrapResponse<T>(response: any): T {
  // 如果响应已经是目标类型（如 CaptchaResponse），直接返回
  if (response && typeof response === 'object') {
    // 检查是否是标准 ApiResponse 格式 { code, message, data }
    if ('code' in response && 'data' in response) {
      if (response.code !== 0) {
        throw new Error(response.message || i18n.t('api.errors.requestFailed'));
      }
      return response.data as T;
    }
    // 如果不是标准格式，直接返回整个响应
    return response as T;
  }
  throw new Error(i18n.t('api.errors.invalidResponse'));
}

export class AuthManager {
  // ========== 配置获取 ==========

  // 获取注册/登录配置
  static async getRegisterConfig(): Promise<RegisterConfig> {
    const response = await api.get<ApiResponse<any>>(`/member/api/register/config`);
    const data = unwrapResponse<any>(response);
    // The register config is nested inside the 'value' property
    return data.value ? data.value as RegisterConfig : data as RegisterConfig;
  }

  // 获取验证码配置
  static async getCaptchaConfig(): Promise<CaptchaConfig> {
    try {
      const response = await api.get<ApiResponse<CaptchaConfig>>(`/member/api/config/getCaptchaConfig`);
      console.log('Captcha config response:', response);
      return unwrapResponse<CaptchaConfig>(response);
    } catch (error: any) {
      console.error('获取验证码配置失败:', error);
      // 如果获取失败，返回默认值（开启验证码）
      return { shop_reception_login: 1 };
    }
  }

  // 获取图形验证码 - 首次获取（不带 captchaId）
  static async getCaptchaSimple(): Promise<CaptchaResponse> {
    return authApi.getCaptcha();
  }

  // 获取图形验证码 - 刷新时使用旧 captcha ID
  static async getCaptcha(captchaId?: string): Promise<CaptchaResponse> {
    return authApi.getCaptcha(captchaId);
  }

  // ========== 手机号登录 ==========

  // 发送手机验证码
  // 参照原 mobile 项目：传递 captcha_id 和 captcha_code
  static async sendMobileCode(
    mobile: string,
    captchaId?: string,
    captchaCode?: string,
    type: 'login' | 'register' | 'reset' = 'login'
  ): Promise<MobileCodeResponse> {
    const body: Record<string, string> = { mobile };
    
    if (captchaId) {
      body.captcha_id = captchaId;
    }
    if (captchaCode) {
      body.captcha_code = captchaCode;
    }
    if (type) {
      body.type = type;
    }
    
    const response = await api.post<ApiResponse<MobileCodeResponse>>(
      `/member/api/login/mobileCode`,
      body
    );
    return unwrapResponse<MobileCodeResponse>(response);
  }

  // 手机号+验证码登录
  static async loginWithMobile(
    mobile: string,
    key: string,
    code: string
  ): Promise<LoginResponse> {
    const response = await api.post<ApiResponse<LoginResponse>>(
      `/member/api/login/mobile`,
      {
        mobile,
        key,
        code,
      }
    );
    return unwrapResponse<LoginResponse>(response);
  }

  // ========== 账号密码登录 ==========

  // 账号密码登录
  static async loginWithAccount(
    username: string,
    password: string,
    captchaId?: string,
    captchaCode?: string
  ): Promise<LoginResponse> {
    const body: Record<string, string> = {
      username,
      password,
    };
    if (captchaId) {
      body.captcha_id = captchaId;
    }
    if (captchaCode) {
      body.captcha_code = captchaCode;
    }
    const response = await api.post<ApiResponse<LoginResponse>>(
      `/member/api/login/login`,
      body
    );
    return unwrapResponse<LoginResponse>(response);
  }

  // ========== 微信登录 ==========

  // 微信授权登录
  static async loginWithWechat(authData: WechatAuthData): Promise<LoginResponse> {
    const response = await api.post<ApiResponse<LoginResponse>>(
      `/member/api/login/auth`,
      authData
    );
    return unwrapResponse<LoginResponse>(response);
  }

  // 微信 Code 登录 (EvoLoop Mobile App 使用)
  static async loginWithWechatCode(
    code: string,
    appType: 'ios' | 'android' = 'ios'
  ): Promise<LoginResponse> {
    const response = await api.post<ApiResponse<LoginResponse>>(
      `/member/api/login/auth`,
      {
        code,
        app_type: appType,
      }
    );
    return unwrapResponse<LoginResponse>(response);
  }

  // 微信+手机号绑定登录
  static async loginWithWechatMobile(
    authData: WechatAuthData,
    mobile: string,
    key: string,
    code: string,
    captchaId?: string,
    captchaCode?: string
  ): Promise<LoginResponse> {
    const body: Record<string, any> = {
      ...authData,
      mobile,
      key,
      code,
    };
    if (captchaId) {
      body.captcha_id = captchaId;
    }
    if (captchaCode) {
      body.captcha_code = captchaCode;
    }
    const response = await api.post<ApiResponse<LoginResponse>>(
      `/member/tripartite/mobile`,
      body
    );
    return unwrapResponse<LoginResponse>(response);
  }

  // ========== 第三方登录绑定手机号 ==========

  // 发送绑定手机号的短信验证码
  static async sendTripartiteMobileCode(
    mobile: string,
    captchaId?: string,
    captchaCode?: string
  ): Promise<MobileCodeResponse> {
    const body: Record<string, string> = { mobile };

    if (captchaId) {
      body.captcha_id = captchaId;
    }
    if (captchaCode) {
      body.captcha_code = captchaCode;
    }

    const response = await api.post<ApiResponse<MobileCodeResponse>>(
      `/member/tripartite/mobileCode`,
      body
    );
    return unwrapResponse<MobileCodeResponse>(response);
  }

  // ========== 用户信息 ==========

  // 获取用户信息
  static async getMemberInfo(): Promise<UserInfo> {
    const response = await api.get<ApiResponse<UserInfo>>(
      `/member/api/member/info`
    );
    return unwrapResponse<UserInfo>(response);
  }

  // ========== Token 管理 ==========

  // 登出（清除服务端会话）
  static async logout(): Promise<void> {
    // 如果后端需要通知登出，可以在这里调用 API
    // await api.post('/api/logout');
  }
}
