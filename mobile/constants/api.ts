// API 端点配置
// 根据 PRD 文档: https://evoloop.develop-assistant.cn

const BASE_URL = 'https://evoloop.develop-assistant.cn';

// ===== Gateway 路由 (Mobile → Gateway → Desktop) =====
// 职责：WebSocket 连接管理、设备状态、指令下发
export const GATEWAY_API = {
  // WebSocket 端点
  WS_URL: `${BASE_URL}/gateway/ws`,
  
  // 基础路径
  BASE: '/gateway/api/v1',
  
  // 设备管理 (Gateway 本地维护)
  DEVICES: '/gateway/api/v1/devices',
  DEVICE_DETAIL: (id: string) => `/gateway/api/v1/devices/${id}`,
  DEVICE_DEFAULT: (id: string) => `/gateway/api/v1/devices/${id}/default`,
  DEVICE_BIND: '/gateway/api/v1/devices/bind',
  
  // 指令下发 (核心 API：转发到 Desktop)
  COMMAND_EXECUTE: '/gateway/api/v1/command/execute',
  
  // 会话控制 (转发到 Desktop)
  CONVERSATION_STOP: (id: string) => `/gateway/api/v1/conversations/${id}/stop`,
  CONVERSATION_REWIND: (id: string) => `/gateway/api/v1/conversations/${id}/rewind`,
  CONVERSATION_RETRY: (id: string) => `/gateway/api/v1/conversations/${id}/retry`,
  
  // HITL (转发到 Desktop)
  HITL_CONFIRM: '/gateway/api/v1/hitl/confirm',
  HITL_CHOICE: '/gateway/api/v1/hitl/choice',
  HITL_TEXT: '/gateway/api/v1/hitl/text',
};

// ===== Member 路由 (业务数据：对话历史、会员、订阅) =====
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
  LOGIN_WECHAT_CODE: '/member/api/login/wechatCodeLogin',  // 微信 Code 登录
  MEMBER_INFO: '/member/api/member/info',
  CHANGE_PASSWORD: '/member/api/member/changePassword',
  SEND_SMS_CODE: '/member/api/member/sendSmsCode',
  BIND_MOBILE: '/member/api/member/bindMobile',
  
  // 订阅管理
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
  
  // ===== 对话历史 (MC 存储 - evolooplink 插件) =====
  CONVERSATIONS: '/evolooplink/api/conversation/list',
  CONVERSATION_DETAIL: (id: string) => `/evolooplink/api/conversation/detail?conversation_id=${id}`,
  CONVERSATION_HISTORY: (id: string) => `/evolooplink/api/conversation/messages?conversation_id=${id}`,
  
  // ===== 删除会话 =====
  CONVERSATION_DELETE: (id: string) => `/evolooplink/api/conversation/delete`,
  
  // ===== 技能 (MC 存储) =====
  SKILLS: '/member/api/skills',
  SKILL_DETAIL: (id: string) => `/member/api/skills/${id}`,
  
  // ===== Artifacts (MC 存储) =====
  ARTIFACTS: '/member/api/artifacts',
  ARTIFACT_DETAIL: (id: string) => `/member/api/artifacts/${id}`,
  
  // ===== 项目管理 =====
  PROJECTS: '/member/api/projects',
  PROJECT_DETAIL: (id: number) => `/member/api/projects/${id}`,
  PROJECT_SWITCH: '/member/api/projects/switch',
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
