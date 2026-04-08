// 应用配置
export const APP_CONFIG = {
  name: 'EvoLoop',
  version: '1.0.0',
  scheme: 'evoloop',
};

// API 配置
export const API_CONFIG = {
  baseURL: process.env.EXPO_PUBLIC_BASE_URL || 'https://evoloop.develop-assistant.cn',
  timeout: 30000,
  retries: 3,
};

// WebSocket 配置
export const WS_CONFIG = {
  reconnectInterval: 3000,
  maxReconnectAttempts: 5,
  heartbeatInterval: 30000,
};

// 微信配置
export const WECHAT_CONFIG = {
  appId: process.env.EXPO_PUBLIC_WECHAT_APP_ID || '',
};

// 音频配置
export const AUDIO_CONFIG = {
  sampleRate: 16000,
  channels: 1,
  bitDepth: 16,
  maxDuration: 60000, // 最大录音时长 60s
};

// NLS 配置（阿里云实时语音识别）
export const NLS_CONFIG = {
  appKey: process.env.EXPO_PUBLIC_NLS_APP_KEY || '',
  url: 'wss://nls-gateway.aliyuncs.com/ws/v1',
  sampleRate: 16000,
  format: 'opus' as const, // opus 或 pcm
};

// 验证码配置
export const CAPTCHA_CONFIG = {
  codeLength: 6,
  countdownSeconds: 120,
};

// 分页配置
export const PAGINATION = {
  defaultPageSize: 20,
  maxPageSize: 100,
};
