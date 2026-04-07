// 微信授权服务

import * as WeChat from 'react-native-wechat-lib';
import { WECHAT_CONFIG } from '@/constants/config';
import { WechatAuthData } from '@/types';

export class WechatAuth {
  private static isRegistered = false;

  // 初始化微信 SDK
  static async init(): Promise<boolean> {
    if (this.isRegistered) {
      return true;
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

      // 发送授权请求
      const authResponse = await WeChat.sendAuthRequest('snsapi_userinfo', '');

      if (!authResponse.code) {
        throw new Error('获取授权码失败');
      }

      // 使用 code 换取 access_token 和 openid
      // 注意：实际项目中，这一步应该在服务端完成，避免暴露 appSecret
      // 这里简化处理，实际应该调用后端接口
      const tokenData = await this.getAccessToken(authResponse.code);

      if (!tokenData.openid) {
        throw new Error('获取用户信息失败');
      }

      // 获取用户信息
      const userInfo = await this.getUserInfo(
        tokenData.access_token,
        tokenData.openid
      );

      return {
        wx_openid: tokenData.openid,
        wx_unionid: tokenData.unionid,
        nickname: userInfo.nickname,
        headimg: userInfo.headimgurl,
      };
    } catch (error) {
      console.error('微信授权失败:', error);
      throw error;
    }
  }

  // 获取 Access Token (应该在服务端完成)
  private static async getAccessToken(code: string): Promise<{
    access_token: string;
    openid: string;
    unionid?: string;
  }> {
    // TODO: 调用后端接口换取 token
    // 不应该在客户端直接调用微信接口，因为需要 appSecret
    throw new Error('请在服务端完成 access_token 换取');
  }

  // 获取用户信息 (应该在服务端完成)
  private static async getUserInfo(
    accessToken: string,
    openId: string
  ): Promise<{
    nickname: string;
    headimgurl: string;
  }> {
    // TODO: 调用后端接口获取用户信息
    throw new Error('请在服务端完成用户信息获取');
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
