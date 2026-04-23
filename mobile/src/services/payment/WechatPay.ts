// 微信支付服务
// 封装微信 APP 支付功能

// 动态导入微信模块，避免在 Expo Go 中崩溃
let WeChat: any = null;
try {
  WeChat = require('react-native-wechat-lib');
} catch (e) {
  console.warn('react-native-wechat-lib 未安装或不可用');
}

import { WECHAT_CONFIG } from '@/constants/config';

// 检查 WeChat 模块是否可用
const isWeChatAvailable = (): boolean => {
  return WeChat !== null && typeof WeChat.registerApp === 'function';
};

// 微信支付参数
export interface WechatPayParams {
  appid: string;
  partnerid: string;
  prepayid: string;
  noncestr: string;
  timestamp: string;
  package: 'Sign=WXPay';
  sign: string;
}

// 支付结果
export interface PayResult {
  success: boolean;
  errCode?: number;
  errStr?: string;
}

/**
 * 微信支付服务
 */
export class WechatPay {
  private static isRegistered = false;

  /**
   * 初始化微信 SDK
   */
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

  /**
   * 检查微信是否已安装
   */
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

  /**
   * 发起微信支付（APP支付）
   * 
   * @param params 微信支付参数
   * @returns Promise<PayResult>
   * 
   * 使用示例：
   * ```
   * const result = await WechatPay.pay({
   *   appid: 'wx...',
   *   partnerid: '123...',
   *   prepayid: 'wx...',
   *   noncestr: '...',
   *   timestamp: '1234567890',
   *   package: 'Sign=WXPay',
   *   sign: '...'
   * });
   * ```
   */
  static async pay(params: WechatPayParams): Promise<PayResult> {
    try {
      // 检查 SDK 是否可用
      if (!isWeChatAvailable()) {
        throw new Error('微信 SDK 不可用');
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

      // 调起微信支付
      const result = await WeChat.pay({
        partnerId: params.partnerid,
        prepayId: params.prepayid,
        nonceStr: params.noncestr,
        timeStamp: params.timestamp,
        package: params.package,
        sign: params.sign,
      });

      // 处理支付结果
      // errCode: 0-成功, -1-错误, -2-用户取消
      if (result.errCode === 0) {
        return { success: true };
      } else if (result.errCode === -2) {
        return { 
          success: false, 
          errCode: result.errCode, 
          errStr: '用户取消支付' 
        };
      } else {
        return { 
          success: false, 
          errCode: result.errCode, 
          errStr: result.errStr || '支付失败' 
        };
      }
    } catch (error: any) {
      console.error('微信支付失败:', error);
      return {
        success: false,
        errStr: error.message || '支付调用失败',
      };
    }
  }

  /**
   * 获取支付错误信息
   */
  static getErrorMessage(errCode?: number): string {
    switch (errCode) {
      case -1:
        return '支付失败，请稍后重试';
      case -2:
        return '您已取消支付';
      default:
        return '支付异常，请稍后重试';
    }
  }
}

// 导出便捷方法
export const payWithWechat = WechatPay.pay.bind(WechatPay);
export const initWechatPay = WechatPay.init.bind(WechatPay);
export const isWechatInstalled = WechatPay.isWXAppInstalled.bind(WechatPay);
