// Type declarations for react-native-dotenv
// These variables are injected from mobile/.env at build time

declare module '@env' {
  export const APP_NAME: string | undefined;
  export const EVOCLOUD_BASE_URL: string | undefined;
  export const EVOCLOUD_BASE_WS_URL: string | undefined;
  export const EVOCLOUD_UNIVERSAL_LINK_URL: string | undefined;
  export const WECHAT_APP_ID: string | undefined;
  export const WECHAT_APP_SECRET: string | undefined;
  export const NLS_APP_KEY: string | undefined;
  export const NLS_WS_URL: string | undefined;
  export const DASHSCOPE_API_KEY: string | undefined;
  export const AMAP_KEY: string | undefined;
}
