// 认证相关类型

export interface UserInfo {
  id: number;
  nickname: string;
  mobile: string;
  email?: string;
  avatar?: string;
  memberLevel: 'free' | 'basic' | 'pro' | 'enterprise';
  memberLevelName: string;
  memberExpireTime?: number;
}

export interface RegisterConfig {
  register: string;
  login: string[];
  third_party: number;
  bind_mobile: number;
  agreement_show: boolean;
  wap_desc: string;
}

export interface CaptchaConfig {
  shop_reception_login: number;
}

export interface CaptchaResponse {
  id: string;
  img: string;
}

export interface MobileCodeRequest {
  mobile: string;
  captcha_id?: string;
  captcha_code?: string;
}

export interface MobileCodeResponse {
  key: string;
}

export interface MobileLoginRequest {
  mobile: string;
  key: string;
  code: string;
}

export interface AccountLoginRequest {
  username: string;
  password: string;
  captcha_id?: string;
  captcha_code?: string;
}

export interface WechatAuthData {
  code?: string;          // 微信授权码
  wx_openid?: string;
  wx_unionid?: string;
  nickname?: string;
  headimg?: string;
}

export interface LoginResponse {
  token: string;
  user: UserInfo;
  can_receive_registergift?: number;
  is_register?: boolean;
}

export interface RegisterRequest {
  mobile: string;
  code: string;
  key: string;
  password?: string;
}

export interface ResetPasswordRequest {
  mobile: string;
  code: string;
  key: string;
  new_password: string;
}

export interface ApiResponse<T = any> {
  code: number;
  message: string;
  data: T;
}
