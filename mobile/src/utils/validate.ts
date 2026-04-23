// 验证工具函数

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
  mobile: '请输入正确的手机号',
  captcha: '验证码格式不正确',
  password: '密码长度至少6位',
  username: '用户名需为3-20位字母或数字',
  email: '邮箱格式不正确',
  required: '此项为必填项',
};
