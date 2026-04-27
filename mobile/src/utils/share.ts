// 系统分享工具 - 调用原生分享面板（iOS UIActivityViewController / Android Intent.ACTION_SEND）
// 用户可在面板上选择微信/钉钉/飞书/邮件/备忘录等任意支持接收文本的应用

import Share from 'react-native-share';

interface ShareOptions {
  /** 分享标题（部分应用显示） */
  title?: string;
  /** 分享内容 */
  message: string;
  /** 分享 URL（可选） */
  url?: string;
}

/**
 * 打开系统分享面板，分享纯文本内容
 * 支持分享到微信、钉钉、飞书、邮件、备忘录等任意应用
 */
export async function shareText(options: ShareOptions): Promise<void> {
  try {
    await Share.open({
      title: options.title || '分享',
      message: options.message,
      url: options.url,
      failOnCancel: false, // 用户取消不抛错
    });
  } catch (error: any) {
    // 用户取消分享时 error?.error?.code === 'ECANCELLED500'
    // 其他错误静默处理，不需要弹窗打扰用户
    if (error?.error?.code !== 'ECANCELLED500') {
      console.warn('分享失败:', error?.message || error);
    }
  }
}

/**
 * 分享单条聊天消息
 */
export async function shareChatMessage(content: string, sender?: string): Promise<void> {
  const message = sender
    ? `${sender}:\n${content}`
    : content;
  await shareText({ title: '分享消息', message });
}

/**
 * 分享代码块
 */
export async function shareCodeBlock(code: string, language?: string): Promise<void> {
  const title = language ? `分享 ${language.toUpperCase()} 代码` : '分享代码';
  await shareText({ title, message: code });
}
