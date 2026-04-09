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
  register: string;         // comma-separated: 'username,mobile'
  login: string;            // comma-separated: 'username,mobile'
  third_party: number;      // 0/1
  bind_mobile: number;      // 0/1
  pwd_len: number;          // min password length, 0 = no restriction
  pwd_complexity: string;   // comma-separated: 'number,letter,upper_case,symbol'
  agreement_show: number;   // 0/1
  wap_bg: string;
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
  captcha_id?: string;
  captcha_code?: string;
  source_member?: string;
  nickname?: string;
  headimg?: string;
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
