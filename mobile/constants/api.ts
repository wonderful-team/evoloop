// API 端点配置

// Member 路由 (认证、订阅) - 需要以 /member 开头
export const MEMBER_API = {
  // 认证
  REGISTER_CONFIG: '/member/api/register/config',
  CAPTCHA_CONFIG: '/member/api/config/getCaptchaConfig',
  CAPTCHA_IMAGE: '/member/api/captcha/captcha',
  SEND_MOBILE_CODE: '/member/api/login/mobileCode',
  LOGIN_MOBILE: '/member/api/login/mobile',
  LOGIN_ACCOUNT: '/member/api/login/login',
  LOGIN_WECHAT: '/member/api/login/auth',
  LOGIN_WECHAT_MOBILE: '/member/api/tripartite/mobileauth',
  MEMBER_INFO: '/member/api/member/info',
  CHANGE_PASSWORD: '/member/api/member/changePassword',
  SEND_SMS_CODE: '/member/api/member/sendSmsCode',
  BIND_MOBILE: '/member/api/member/bindMobile',
  
  // 订阅
  SUBSCRIPTION_STATUS: '/member/subscription/api/subscription/status',
  SUBSCRIPTION_DETAIL: '/member/subscription/api/subscription/getDetail',
  SUBSCRIPTION_PLANS: '/member/subscription/api/subscription/plans',
  SUBSCRIPTION_BENEFITS: '/member/subscription/api/subscription/benefits',
  CREATE_ORDER: '/member/subscription/api/order/create',
  CALCULATE_UPGRADE: '/member/subscription/api/plan/calculateUpgradePrice',
  
  // 支付
  PAY_INFO: '/member/api/pay/info',
  PAY: '/member/api/pay/pay',
  PAY_STATUS: '/member/api/pay/status',
  
  // 上传
  UPLOAD_CHAT_IMAGE: '/member/api/upload/chatimg',
  UPLOAD_CHAT_FILE: '/member/api/upload/chatfile',
};

// Gateway 路由 (设备、项目、对话)
export const GATEWAY_API = {
  // WebSocket
  WS_URL: '/gateway/ws',
  
  // 设备
  DEVICES: '/gateway/api/v1/devices',
  DEVICE_BIND: '/gateway/api/v1/devices/bind',
  DEVICE_DETAIL: (id: string) => `/gateway/api/v1/devices/${id}`,
  
  // 项目
  PROJECTS: '/gateway/api/v1/projects',
  PROJECT_SWITCH: '/gateway/api/v1/projects/switch',
  PROJECT_DETAIL: (id: number) => `/gateway/api/v1/projects/${id}`,
  
  // 指令
  COMMANDS: '/gateway/api/v1/commands',
  COMMAND_SEND: '/gateway/api/v1/commands/send',
};

// HTTP 状态码
export const HTTP_STATUS = {
  OK: 200,
  CREATED: 201,
  BAD_REQUEST: 400,
  UNAUTHORIZED: 401,
  FORBIDDEN: 403,
  NOT_FOUND: 404,
  SERVER_ERROR: 500,
};
