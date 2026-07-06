// 格式化工具函数

import i18n from '@/locales';
import { format, formatDistanceToNow } from 'date-fns';
import { zhCN, enUS } from 'date-fns/locale';

function getDateFnsLocale() {
  const lang = i18n.language || 'en';
  return lang.startsWith('zh') ? zhCN : enUS;
}

function getNumberLocale(): string {
  const lang = i18n.language || 'en';
  return lang.startsWith('zh') ? 'zh-CN' : 'en-US';
}

function safeDate(input: number | Date | string | null | undefined): Date | null {
  if (!input) {return null;}
  const d = new Date(input);
  return isNaN(d.getTime()) ? null : d;
}

// 日期格式化
export const formatDate = {
  // 完整日期时间
  full: (timestamp: number | Date | string | null | undefined): string => {
    const d = safeDate(timestamp);
    return d
      ? format(d, i18n.t('format.dateTime.full'), { locale: getDateFnsLocale() })
      : i18n.t('format.dateTime.empty');
  },

  // 日期
  date: (timestamp: number | Date | string | null | undefined): string => {
    const d = safeDate(timestamp);
    return d
      ? format(d, i18n.t('format.dateTime.date'), { locale: getDateFnsLocale() })
      : i18n.t('format.dateTime.empty');
  },

  // 时间
  time: (timestamp: number | Date | string | null | undefined): string => {
    const d = safeDate(timestamp);
    return d
      ? format(d, i18n.t('format.dateTime.time'), { locale: getDateFnsLocale() })
      : i18n.t('format.dateTime.empty');
  },

  // 相对时间 (如：3分钟前)
  relative: (timestamp: number | Date | string | null | undefined): string => {
    const d = safeDate(timestamp);
    return d ? formatDistanceToNow(d, {
      addSuffix: true,
      locale: getDateFnsLocale(),
    }) : i18n.t('format.dateTime.empty');
  },
};

// 金额格式化
export const formatMoney = {
  // 人民币格式
  cny: (amount: number | string): string => {
    const num = typeof amount === 'string' ? parseFloat(amount) : amount;
    const symbol = i18n.t('format.currencySymbol');
    const formatted = num.toLocaleString(getNumberLocale(), {
      minimumFractionDigits: 2,
      maximumFractionDigits: 2,
    });
    return `${symbol}${formatted}`;
  },

  // 简化格式 (元)
  yuan: (amount: number | string): string => {
    const num = typeof amount === 'string' ? parseFloat(amount) : amount;
    return `${num.toFixed(0)}${i18n.t('format.currencyUnit')}`;
  },
};

// 数字格式化
export const formatNumber = {
  // 千分位
  thousand: (num: number): string => {
    return num.toLocaleString(getNumberLocale());
  },

  // 文件大小
  fileSize: (bytes: number): string => {
    if (bytes === 0) {
      const units = i18n.t('common.fileSize.units', { returnObjects: true }) as string[];
      return `0 ${units[0]}`;
    }
    const k = 1024;
    const sizes = i18n.t('common.fileSize.units', { returnObjects: true }) as string[];
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
  if (!mobile || mobile.length !== 11) {return mobile;}
  return `${mobile.slice(0, 3)}****${mobile.slice(7)}`;
};

// 截断文本
export const truncate = (text: string, maxLength: number): string => {
  if (text.length <= maxLength) {return text;}
  return `${text.slice(0, maxLength)}${i18n.t('common.ellipsis')}`;
};
