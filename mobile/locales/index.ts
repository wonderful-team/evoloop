// i18n 配置

import i18n from 'i18next';
import { initReactI18next } from 'react-i18next';
import * as Localization from 'expo-localization';

import zh from './zh.json';
import en from './en.json';

const resources = {
  'zh-CN': { translation: zh },
  'zh-TW': { translation: zh },
  'zh-HK': { translation: zh },
  'en-US': { translation: en },
  'en': { translation: en },
};

i18n
  .use(initReactI18next)
  .init({
    resources,
    lng: Localization.locale,
    fallbackLng: 'zh-CN',
    interpolation: {
      escapeValue: false,
    },
    react: {
      useSuspense: false,
    },
    // 使用 compatibilityJSON v3 避免 Intl API 警告
    compatibilityJSON: 'v3',
  });

export default i18n;
