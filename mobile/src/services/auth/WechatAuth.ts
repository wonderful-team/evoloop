// 微信授权服务 - 参照 mobile_uniapp 实现
// 流程：App 获取 code → 用 code 换 access_token/openid → 获取用户信息 → 传给后端 /api/login/auth

// 动态导入微信模块，避免在 Expo Go 中崩溃
let WeChat: any = null;
try {
  WeChat = require('react-native-wechat-lib');
} catch (e) {
  console.warn('react-native-wechat-lib 未安装或不可用');
}

import { WECHAT_CONFIG, UNIVERSAL_LINK_URL } from '@/constants/config';
import { api } from '@/services/api/client';
import { ApiResponse } from '@/types';
import i18n from '@/locales';

// 检查 WeChat 模块是否可用
const isWeChatAvailable = (): boolean => {
  return WeChat !== null && typeof WeChat.registerApp === 'function';
};

// 微信 access_token 响应
interface WechatAccessTokenResponse {
  access_token: string;
  expires_in: number;
  refresh_token: string;
  openid: string;
  scope: string;
  unionid?: string;
  errcode?: number;
  errmsg?: string;
}

// 微信用户信息响应
interface WechatUserInfoResponse {
  openid: string;
  nickname: string;
  sex: number;
  province: string;
  city: string;
  country: string;
  headimgurl: string;
  privilege: string[];
  unionid?: string;
  errcode?: number;
  errmsg?: string;
}

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
        UNIVERSAL_LINK_URL
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

  // 发起微信授权，获取 code
  static async authorize(): Promise<string> {
    try {
      if (!isWeChatAvailable()) {
        throw new Error(i18n.t('auth.errors.wechatSdkUnavailable'));
      }

      if (!this.isRegistered) {
        const initialized = await this.init();
        if (!initialized) {
          throw new Error(i18n.t('auth.errors.wechatSdkInitFailed'));
        }
      }

      const isInstalled = await this.isWXAppInstalled();
      if (!isInstalled) {
        throw new Error(i18n.t('auth.errors.wechatNotInstalled'));
      }

      // 发送授权请求，获取 code（snsapi_userinfo 获取用户信息）
      const authResponse = await WeChat.sendAuthRequest('snsapi_userinfo', '');

      if (!authResponse.code) {
        throw new Error(i18n.t('auth.errors.authCodeFailed'));
      }

      return authResponse.code;
    } catch (error) {
      console.error('微信授权失败:', error);
      throw error;
    }
  }

  // 用 code 换取 access_token 和 openid（调微信服务器）
  private static async getAccessToken(code: string): Promise<WechatAccessTokenResponse> {
    const url = `https://api.weixin.qq.com/sns/oauth2/access_token?appid=${WECHAT_CONFIG.appId}&secret=${WECHAT_CONFIG.appSecret}&code=${code}&grant_type=authorization_code`;

    const response = await fetch(url);
    const data: WechatAccessTokenResponse = await response.json();

    if (data.errcode) {
      throw new Error(i18n.t('auth.errors.wechatApiError', { message: data.errmsg || data.errcode }));
    }

    if (!data.access_token || !data.openid) {
      throw new Error(i18n.t('auth.errors.getTokenFailed'));
    }

    return data;
  }

  // 用 access_token 换取用户信息（调微信服务器）
  private static async getUserInfo(
    accessToken: string,
    openid: string
  ): Promise<WechatUserInfoResponse> {
    const url = `https://api.weixin.qq.com/sns/userinfo?access_token=${accessToken}&openid=${openid}`;

    const response = await fetch(url);
    const data: WechatUserInfoResponse = await response.json();

    if (data.errcode) {
      throw new Error(i18n.t('auth.errors.wechatApiError', { message: data.errmsg || data.errcode }));
    }

    return data;
  }

  // 完整的微信登录流程（参照 mobile_uniapp）
  static async login(appType: 'ios' | 'android' = 'ios'): Promise<WechatLoginResult> {
    // 步骤1: 获取微信授权 code
    const code = await this.authorize();

    if (!WECHAT_CONFIG.appSecret) {
      throw new Error(i18n.t('auth.errors.appSecretNotConfigured'));
    }

    // 步骤2: 用 code 换 access_token + openid + unionid
    const tokenData = await this.getAccessToken(code);

    // 步骤3: 用 access_token 获取用户信息
    const userInfo = await this.getUserInfo(tokenData.access_token, tokenData.openid);

    // 步骤4: 传给后端 /api/login/auth（参照 mobile_uniapp 的 authLogin）
    const authData = {
      wx_openid: userInfo.openid,
      wx_unionid: userInfo.unionid || tokenData.unionid || '',
      nickname: userInfo.nickname,
      headimg: userInfo.headimgurl,
      app_type: appType,
    };

    // 步骤5: 调用后端登录接口
    const response = await api.post<ApiResponse<WechatLoginResult>>(
      `/member/api/login/auth`,
      authData
    );

    if (response.code !== 0) {
      // 后端返回 MEMBER_NOT_EXIST 时，需要绑定手机号
      if (response.data === 'MEMBER_NOT_EXIST' as any) {
        return {
          token: '',
          need_bind_mobile: true,
          wx_openid: authData.wx_openid,
          wx_unionid: authData.wx_unionid,
          nickname: authData.nickname,
          avatar: authData.headimg,
        } as WechatLoginResult;
      }
      throw new Error(response.message || i18n.t('auth.errors.wechatLoginFailed'));
    }

    return response.data;
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
