// 认证管理服务

import { api } from '@/services/api/client';
import { MEMBER_API } from '@/constants/api';
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
        throw new Error(response.message || '请求失败');
      }
      return response.data as T;
    }
    // 如果不是标准格式，直接返回整个响应
    return response as T;
  }
  throw new Error('无效的响应数据');
}

export class AuthManager {
  // ========== 配置获取 ==========

  // 获取注册/登录配置
  static async getRegisterConfig(): Promise<RegisterConfig> {
    const response = await api.get<ApiResponse<RegisterConfig>>(
      MEMBER_API.REGISTER_CONFIG
    );
    return unwrapResponse<RegisterConfig>(response);
  }

  // 获取验证码配置
  static async getCaptchaConfig(): Promise<CaptchaConfig> {
    try {
      const response = await api.get<ApiResponse<CaptchaConfig>>(
        MEMBER_API.CAPTCHA_CONFIG
      );
      console.log('Captcha config response:', response);
      return unwrapResponse<CaptchaConfig>(response);
    } catch (error: any) {
      console.error('获取验证码配置失败:', error);
      // 如果获取失败，返回默认值（开启验证码）
      return { shop_reception_login: 1 };
    }
  }

  // 注意：后端部署的验证码接口返回 PNG 图片而不是 JSON
  // 这是因为后端 ThinkCaptcha::create() 缺少第二个参数 true
  // 需要后端修复才能正常使用验证码功能
  
  // 获取图形验证码 - 尝试后端修复后的 JSON 格式
  static async getCaptchaSimple(): Promise<CaptchaResponse> {
    try {
      const response = await api.get<ApiResponse<CaptchaResponse>>(
        MEMBER_API.CAPTCHA_IMAGE
      );
      
      console.log('Captcha simple response:', response);
      
      return unwrapResponse<CaptchaResponse>(response);
    } catch (error: any) {
      console.error('获取图形验证码失败:', error);
      // 如果后端返回 PNG 而不是 JSON，会解析失败
      throw new Error('验证码服务暂时不可用，请联系管理员修复后端配置');
    }
  }

  // 获取图形验证码 - 刷新时使用旧 captcha ID
  static async getCaptcha(captchaId?: string): Promise<CaptchaResponse> {
    try {
      // 参照原 mobile 项目：传递 { id: captchaId }，但后端实际使用 captcha_id
      const params: Record<string, string> = {};
      if (captchaId) {
        params.captcha_id = captchaId;
      }
      
      const response = await api.get<ApiResponse<CaptchaResponse>>(
        MEMBER_API.CAPTCHA_IMAGE,
        Object.keys(params).length > 0 ? { params } : undefined
      );
      
      console.log('Captcha response:', response);
      
      return unwrapResponse<CaptchaResponse>(response);
    } catch (error: any) {
      console.error('获取图形验证码失败:', error);
      throw new Error('验证码服务暂时不可用，请联系管理员修复后端配置');
    }
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
      MEMBER_API.SEND_MOBILE_CODE,
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
      MEMBER_API.LOGIN_MOBILE,
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
    captchaCode?: string
  ): Promise<LoginResponse> {
    const response = await api.post<ApiResponse<LoginResponse>>(
      MEMBER_API.LOGIN_ACCOUNT,
      {
        username,
        password,
        captcha_code: captchaCode,
      }
    );
    return unwrapResponse<LoginResponse>(response);
  }

  // ========== 微信登录 ==========

  // 微信授权登录
  static async loginWithWechat(authData: WechatAuthData): Promise<LoginResponse> {
    const response = await api.post<ApiResponse<LoginResponse>>(
      MEMBER_API.LOGIN_WECHAT,
      authData
    );
    return unwrapResponse<LoginResponse>(response);
  }

  // 微信+手机号绑定登录
  static async loginWithWechatMobile(
    authData: WechatAuthData,
    mobile: string,
    key: string,
    code: string
  ): Promise<LoginResponse> {
    const response = await api.post<ApiResponse<LoginResponse>>(
      MEMBER_API.LOGIN_WECHAT_MOBILE,
      {
        ...authData,
        mobile,
        key,
        code,
      }
    );
    return unwrapResponse<LoginResponse>(response);
  }

  // ========== 用户信息 ==========

  // 获取用户信息
  static async getMemberInfo(): Promise<UserInfo> {
    const response = await api.get<ApiResponse<UserInfo>>(
      MEMBER_API.MEMBER_INFO
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
