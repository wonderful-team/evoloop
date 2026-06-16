// i18n 配置

import i18n from 'i18next';
import { initReactI18next } from 'react-i18next';
import * as RNLocalize from 'react-native-localize';

import zh from './zh.json';
import en from './en.json';

if (typeof Intl === 'undefined') {
  (globalThis as any).Intl = {
    PluralRules: class {
      select(n: number) {
        return n === 1 ? 'one' : 'other';
      }
      resolvedOptions() {
        return { pluralCategories: ['one', 'other'] };
      }
    },
  };
} else if (typeof Intl.PluralRules === 'undefined') {
  (Intl as any).PluralRules = class {
    select(n: number) {
      return n === 1 ? 'one' : 'other';
    }
    resolvedOptions() {
      return { pluralCategories: ['one', 'other'] };
    }
  };
}

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
  });

export default i18n;
