// 通用类型定义

import i18n from '@/locales';

// ========== 认证相关类型 ==========

export interface UserInfo {
  id: number;
  nickname: string;
  mobile: string;
  email?: string;
  avatar?: string;
  memberLevel: 'free' | 'basic' | 'pro' | 'enterprise';
  memberLevelName: string;
  memberExpireTime?: number;
  balance?: string;
  point?: number;
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
  shop_reception_login?: number;
  shop_reception_register?: number;
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
  user?: UserInfo;
  can_receive_registergift?: number;
  is_register?: boolean;
  need_bind_mobile?: boolean;
  wx_openid?: string;
  wx_unionid?: string;
  nickname?: string;
  avatar?: string;
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

// ========== 项目相关类型 ==========

export interface Project {
  id: number;
  name: string;
  description?: string;
  rootPath?: string;
  isActive?: boolean;
  isGlobal?: boolean;
  createdAt?: string;
  updatedAt?: string;
}

// 虚拟全局项目（跨项目对话模式）
export const GLOBAL_PROJECT: Project = {
  id: 0,
  name: i18n.t('projects.globalModeName'),
  description: i18n.t('projects.globalModeDesc'),
  rootPath: '',
  isActive: false,
  isGlobal: true,
};

export const isGlobalProject = (project: Project | null): boolean => {
  return project?.id === 0 || project?.isGlobal === true;
};

// ========== 设备相关类型 ==========

export interface Device {
  deviceKey: string;
  name: string;
  status: 'online' | 'offline' | 'busy';
  type?: string;
  lastSeen?: string;
}

export interface DeviceBindingRequest {
  deviceKey: string;
  code: string;
}

export interface DeviceCommandRequest {
  deviceKey: string;
  command: {
    type: string;
    params: any;
  };
}

// ========== 项目流转相关类型 ==========

export interface ProjectSwitchRequest {
  deviceKey: string;
  projectId: number;
}

export interface ProjectSwitchResponse {
  success: boolean;
  message: string;
}

// ========== 技能执行相关类型 ==========

export interface SkillExecutionRequest {
  deviceKey: string;
  skillId: string;
  params?: Record<string, any>;
}

export interface SkillExecutionResponse {
  code: number;
  message: string;
}
