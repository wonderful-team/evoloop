// 格式化工具函数

import { format, formatDistanceToNow } from 'date-fns';
import { zhCN } from 'date-fns/locale';

function safeDate(input: number | Date | string | null | undefined): Date | null {
  if (!input) return null;
  const d = new Date(input);
  return isNaN(d.getTime()) ? null : d;
}

// 日期格式化
export const formatDate = {
  // 完整日期时间
  full: (timestamp: number | Date | string | null | undefined): string => {
    const d = safeDate(timestamp);
    return d ? format(d, 'yyyy-MM-dd HH:mm:ss') : '--';
  },

  // 日期
  date: (timestamp: number | Date | string | null | undefined): string => {
    const d = safeDate(timestamp);
    return d ? format(d, 'yyyy-MM-dd') : '--';
  },

  // 时间
  time: (timestamp: number | Date | string | null | undefined): string => {
    const d = safeDate(timestamp);
    return d ? format(d, 'HH:mm') : '--';
  },

  // 相对时间 (如：3分钟前)
  relative: (timestamp: number | Date | string | null | undefined): string => {
    const d = safeDate(timestamp);
    return d ? formatDistanceToNow(d, {
      addSuffix: true,
      locale: zhCN,
    }) : '--';
  },
};

// 金额格式化
export const formatMoney = {
  // 人民币格式
  cny: (amount: number | string): string => {
    const num = typeof amount === 'string' ? parseFloat(amount) : amount;
    return `¥${num.toFixed(2)}`;
  },
  
  // 简化格式 (元)
  yuan: (amount: number | string): string => {
    const num = typeof amount === 'string' ? parseFloat(amount) : amount;
    return `${num.toFixed(0)}元`;
  },
};

// 数字格式化
export const formatNumber = {
  // 千分位
  thousand: (num: number): string => {
    return num.toLocaleString('zh-CN');
  },
  
  // 文件大小
  fileSize: (bytes: number): string => {
    if (bytes === 0) return '0 B';
    const k = 1024;
    const sizes = ['B', 'KB', 'MB', 'GB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return `${(bytes / Math.pow(k, i)).toFixed(2)} ${sizes[i]}`;
  },
  
  // 时长格式化 (秒 -> mm:ss)
  duration: (seconds: number): string => {
    const mins = Math.floor(seconds / 60);
    const secs = seconds % 60;
    return `${mins.toString().padStart(2, '0')}:${secs.toString().padStart(2, '0')}`;
  },
};

// 手机号脱敏
export const maskMobile = (mobile: string): string => {
  if (!mobile || mobile.length !== 11) return mobile;
  return `${mobile.slice(0, 3)}****${mobile.slice(7)}`;
};

// 截断文本
export const truncate = (text: string, maxLength: number): string => {
  if (text.length <= maxLength) return text;
  return `${text.slice(0, maxLength)}...`;
};
