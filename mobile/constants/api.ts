// API 端点配置
// 根据 PRD 文档: https://evoloop.develop-assistant.cn

const BASE_URL = 'https://evoloop.develop-assistant.cn';

// ===== Gateway 路由 (聊天对话、设备管理、项目管理) =====
// 通过 evoloop/backend 转发到各服务
export const GATEWAY_API = {
  // WebSocket 聊天对话
  WS_URL: `${BASE_URL}/gateway/ws`,
  
  // 基础路径
  BASE: '/gateway/api/v1',
  
  // 设备管理
  DEVICES: '/gateway/api/v1/devices',
  DEVICE_BIND: '/gateway/api/v1/devices/bind',
  DEVICE_DETAIL: (id: string) => `/gateway/api/v1/devices/${id}`,
  
  // 项目管理
  PROJECTS: '/gateway/api/v1/projects',
  PROJECT_SWITCH: '/gateway/api/v1/projects/switch',
  PROJECT_DETAIL: (id: number) => `/gateway/api/v1/projects/${id}`,
  
  // 指令下发
  COMMANDS: '/gateway/api/v1/commands',
  COMMAND_SEND: '/gateway/api/v1/commands/send',
  
  // 会话/对话管理 (通过 Gateway 转发)
  CONVERSATIONS: '/gateway/api/v1/conversations',
  CONVERSATION_DETAIL: (id: string) => `/gateway/api/v1/conversations/${id}`,
  CONVERSATION_HISTORY: (id: string) => `/gateway/api/v1/conversations/${id}/history`,
  CONVERSATION_STOP: (id: string) => `/gateway/api/v1/conversations/${id}/stop`,
  CONVERSATION_REWIND: (id: string) => `/gateway/api/v1/conversations/${id}/rewind`,
  CONVERSATION_RETRY: (id: string) => `/gateway/api/v1/conversations/${id}/retry`,
  
  // Artifacts (通过 Gateway 转发)
  ARTIFACTS: '/gateway/api/v1/artifacts',
  ARTIFACT_DETAIL: (id: string) => `/gateway/api/v1/artifacts/${id}`,
  
  // Skills (通过 Gateway 转发)
  SKILLS: '/gateway/api/v1/skills',
  SKILL_EXECUTE: '/gateway/api/v1/skills/execute',
  SKILL_EXECUTION: (id: string) => `/gateway/api/v1/skills/execution/${id}`,
  MCP_SERVERS: '/gateway/api/v1/mcp/servers',
  
  // 模型管理
  MODELS: '/gateway/api/v1/models',
  USAGE_QUOTA: '/gateway/api/v1/usage/quota',
  USAGE_TOKENS: '/gateway/api/v1/usage/tokens',
};

// ===== Member 路由 (认证、订阅) =====
// 直接访问 member-center/backend
export const MEMBER_API = {
  BASE: `${BASE_URL}/member`,
  
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
  
  // 订阅管理 (通过 Gateway 转发到 member-center)
  SUBSCRIPTION_STATUS: '/member/subscription/api/subscription/status',
  SUBSCRIPTION_DETAIL: '/member/subscription/api/subscription/getDetail',
  SUBSCRIPTION_PLANS: '/member/subscription/api/subscription/plans',
  SUBSCRIPTION_BENEFITS: '/member/subscription/api/subscription/benefits',
  SUBSCRIPTION_CHECK_BENEFIT: '/member/subscription/api/subscription/checkBenefit',
  SUBSCRIPTION_CHECK_PERMISSION: '/member/subscription/api/subscription/checkPermission',
  CREATE_ORDER: '/member/subscription/api/order/create',
  CALCULATE_UPGRADE: '/member/subscription/api/plan/calculateUpgradePrice',
  ORDER_STATUS: '/member/subscription/api/order/checkStatus',
  CANCEL_SUBSCRIPTION: '/member/subscription/api/subscription/cancel',
  
  // AI 配额
  AI_QUOTA: '/member/subscription/api/aiQuota',
  AI_QUOTA_HISTORY: '/member/subscription/api/aiQuota/getUsageHistory',
  
  // 上传
  UPLOAD_CHAT_IMAGE: '/member/api/upload/chatimg',
  UPLOAD_CHAT_FILE: '/member/api/upload/chatfile',
  
  // 项目记忆 (通过 Gateway)
  PROJECT_MEMORY: (projectId: number) => `/member/api/projects/${projectId}/memory`,
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

// 导出完整 URL 构建器
export const API_URLS = {
  gateway: (path: string) => `${BASE_URL}${path}`,
  member: (path: string) => `${BASE_URL}${path}`,
  websocket: () => GATEWAY_API.WS_URL,
};

// 权益编码 (Mobile 端)
export const MOBILE_BENEFIT_CODES = {
  AI_QUOTA: 'ai_quota',
  AI_ADVANCED: 'ai_advanced',
  VOICE: 'voice',
  PROJECT_LIMIT: 'project_limit',
  GANTT: 'gantt',
  TIMESHEET: 'timesheet',
} as const;

// 权益到套餐的映射
export const BENEFIT_PLAN_MAP: Record<string, string> = {
  ai_quota: '探索者版',
  ai_advanced: '极客版',
  voice: '极客版',
  project_limit: '探索者版',
  gantt: '企业版',
  timesheet: '企业版',
};

// 权益中文名称
export const BENEFIT_NAME_MAP: Record<string, string> = {
  ai_quota: 'AI 调用额度',
  ai_advanced: '高级模型',
  voice: '语音交互',
  project_limit: '项目数量',
  gantt: '甘特图',
  timesheet: '工时表',
};
