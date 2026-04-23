// i18n 配置

import i18n from 'i18next';
import { initReactI18next } from 'react-i18next';
import * as RNLocalize from 'react-native-localize';

import zh from './zh.json';
import en from './en.json';

const resources = {
  'zh': { translation: zh },
  'zh-CN': { translation: zh },
  'zh-TW': { translation: zh },
  'zh-HK': { translation: zh },
  'en': { translation: en },
  'en-US': { translation: en },
  'en-GB': { translation: en },
};

const locale = RNLocalize.getLocales()[0]?.languageTag || 'zh-CN';

i18n
  .use(initReactI18next)
  .init({
    resources,
    lng: locale,
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
