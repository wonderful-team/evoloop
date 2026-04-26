// 应用配置
import {
  APP_NAME,
  EVOCLOUD_BASE_URL,
  EVOCLOUD_BASE_WS_URL,
  EVOCLOUD_UNIVERSAL_LINK_URL,
  WECHAT_APP_ID,
  WECHAT_APP_SECRET,
  NLS_APP_KEY,
  NLS_WS_URL,
  AMAP_KEY,
} from '@env';

export const APP_CONFIG = {
  name: APP_NAME,
  version: '1.0.0',
  scheme: 'evoloop',
};

// API 配置
export const API_CONFIG = {
  baseURL: EVOCLOUD_BASE_URL || 'http://127.0.0.1',
  timeout: 30000,
  retries: 3,
};

export const BASE_URL = API_CONFIG.baseURL;
export const GATEWAY_BASE_URL = `${API_CONFIG.baseURL}/gateway`;

// WebSocket 配置
// NOTE: Metro cache-bust marker v2
export const WS_CONFIG = {
  baseURL: EVOCLOUD_BASE_WS_URL || 'ws://127.0.0.1',
  reconnectBaseInterval: 2000,   // 首次重连等待 2s
  reconnectMaxInterval: 60000,   // 最长间隔 60s
  heartbeatInterval: 30000,
};

export const WS_BASE_URL = WS_CONFIG.baseURL;

// 微信 Universal Link
export const UNIVERSAL_LINK_URL = EVOCLOUD_UNIVERSAL_LINK_URL || `${EVOCLOUD_BASE_URL}/universal-link`;

// 微信配置
export const WECHAT_CONFIG = {
  appId: WECHAT_APP_ID || '',
  appSecret: WECHAT_APP_SECRET || '',
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
  appKey: NLS_APP_KEY || '',
  url: NLS_WS_URL || 'wss://nls-gateway.aliyuncs.com/ws/v1',
  sampleRate: 16000,
  format: 'opus' as const, // opus 或 pcm
};

// 高德地图配置
export const AMAP_CONFIG = {
  key: AMAP_KEY || '',
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
