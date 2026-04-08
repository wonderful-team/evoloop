// 微信授权服务

// 动态导入微信模块，避免在 Expo Go 中崩溃
let WeChat: any = null;
try {
  WeChat = require('react-native-wechat-lib');
} catch (e) {
  console.warn('react-native-wechat-lib 未安装或不可用');
}

import { WECHAT_CONFIG } from '@/constants/config';
import { WechatAuthData } from '@/types';
import { api } from '@/services/api/client';
import { MEMBER_API } from '@/constants/api';
import { ApiResponse } from '@/types';

// 检查 WeChat 模块是否可用
const isWeChatAvailable = (): boolean => {
  return WeChat !== null && typeof WeChat.registerApp === 'function';
};

export interface WechatLoginResult {
  token: string;
  can_receive_registergift?: number;
  is_register?: number;
  need_bind_mobile?: boolean;
  wx_openid?: string;
  wx_unionid?: string;
  nickname?: string;
  avatar?: string;
}

export class WechatAuth {
  private static isRegistered = false;

  // 初始化微信 SDK
  static async init(): Promise<boolean> {
    if (this.isRegistered) {
      return true;
    }

    if (!isWeChatAvailable()) {
      console.warn('微信 SDK 不可用（可能在 Expo Go 中运行）');
      return false;
    }

    try {
      const result = await WeChat.registerApp(
        WECHAT_CONFIG.appId,
        'https://evoloop.develop-assistant.cn/universal-link'
      );
      this.isRegistered = result;
      return result;
    } catch (error) {
      console.error('微信 SDK 初始化失败:', error);
      return false;
    }
  }

  // 检查微信是否已安装
  static async isWXAppInstalled(): Promise<boolean> {
    if (!isWeChatAvailable()) {
      return false;
    }
    try {
      return await WeChat.isWXAppInstalled();
    } catch (error) {
      console.error('检查微信安装状态失败:', error);
      return false;
    }
  }

  // 发起微信授权登录
  static async authorize(): Promise<WechatAuthData | null> {
    try {
      // 检查 SDK 是否可用
      if (!isWeChatAvailable()) {
        throw new Error('微信 SDK 不可用，请使用 Development Build 运行');
      }

      // 确保已初始化
      if (!this.isRegistered) {
        const initialized = await this.init();
        if (!initialized) {
          throw new Error('微信 SDK 初始化失败');
        }
      }

      // 检查微信是否安装
      const isInstalled = await this.isWXAppInstalled();
      if (!isInstalled) {
        throw new Error('请先安装微信');
      }

      // 发送授权请求，获取 code
      const authResponse = await WeChat.sendAuthRequest('snsapi_userinfo', '');

      if (!authResponse.code) {
        throw new Error('获取授权码失败');
      }

      // 返回 code，由上层调用后端接口换取 token
      return {
        code: authResponse.code,
        wx_openid: '',
        wx_unionid: '',
        nickname: '',
        headimg: '',
      };
    } catch (error) {
      console.error('微信授权失败:', error);
      throw error;
    }
  }

  // 使用 code 登录后端
  static async loginWithCode(code: string, appType: 'ios' | 'android' = 'ios'): Promise<WechatLoginResult> {
    try {
      const response = await api.post<ApiResponse<WechatLoginResult>>(
        MEMBER_API.LOGIN_AUTH,
        {
          code,
          app_type: appType,
        }
      );

      if (response.code !== 0) {
        throw new Error(response.message || '微信登录失败');
      }

      return response.data;
    } catch (error: any) {
      console.error('微信登录请求失败:', error);
      throw new Error(error.message || '微信登录请求失败');
    }
  }

  // 完整的微信登录流程
  static async login(appType: 'ios' | 'android' = 'ios'): Promise<WechatLoginResult> {
    // 1. 获取微信授权 code
    const authData = await this.authorize();
    if (!authData || !authData.code) {
      throw new Error('获取微信授权失败');
    }

    // 2. 使用 code 登录后端
    return await this.loginWithCode(authData.code, appType);
  }

  // 分享文本到微信
  static async shareText(
    text: string,
    scene: 'session' | 'timeline' | 'favorite' = 'session'
  ): Promise<boolean> {
    try {
      const result = await WeChat.shareText({
        text,
        scene: this.getScene(scene),
      });
      return result;
    } catch (error) {
      console.error('分享失败:', error);
      return false;
    }
  }

  // 分享图片到微信
  static async shareImage(
    imageUrl: string,
    scene: 'session' | 'timeline' | 'favorite' = 'session'
  ): Promise<boolean> {
    try {
      const result = await WeChat.shareImage({
        imageUrl,
        scene: this.getScene(scene),
      });
      return result;
    } catch (error) {
      console.error('分享失败:', error);
      return false;
    }
  }

  // 获取分享场景
  private static getScene(
    scene: 'session' | 'timeline' | 'favorite'
  ): number {
    switch (scene) {
      case 'session':
        return WeChat.Scene.Session;
      case 'timeline':
        return WeChat.Scene.Timeline;
      case 'favorite':
        return WeChat.Scene.Favorite;
      default:
        return WeChat.Scene.Session;
    }
  }
}

// 场景常量
export const WechatScene = {
  Session: 0, // 聊天界面
  Timeline: 1, // 朋友圈
  Favorite: 2, // 收藏
} as const;
