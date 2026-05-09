// 验证工具函数

import i18n from '@/locales';

export const validate = {
  // 手机号验证 (中国大陆)
  mobile: (value: string): boolean => {
    return /^1[3-9]\d{9}$/.test(value);
  },
  
  // 验证码验证 (4-6位数字)
  captcha: (value: string): boolean => {
    return /^\d{4,6}$/.test(value);
  },
  
  // 密码验证 (至少6位)
  password: (value: string): boolean => {
    return value.length >= 6;
  },
  
  // 用户名验证 (字母/数字，3-20位)
  username: (value: string): boolean => {
    return /^[a-zA-Z0-9]{3,20}$/.test(value);
  },
  
  // 邮箱验证
  email: (value: string): boolean => {
    return /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(value);
  },
  
  // 不能为空
  required: (value: string): boolean => {
    return value.trim().length > 0;
  },
};

// 表单验证错误消息
export const validateMessages = {
  mobile: i18n.t('validation.mobile'),
  captcha: i18n.t('validation.captcha'),
  password: i18n.t('validation.password'),
  username: i18n.t('validation.username'),
  email: i18n.t('validation.email'),
  required: i18n.t('validation.required'),
};
