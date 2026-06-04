/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_API_URL: string
  readonly VITE_EVOCLOUD_MEMBER_BASE_URL: string
  /**
   * 启动页面调试模式
   * - "true": 显示终端窗口（带日志输出）
   * - "false": 显示简洁 LOGO + 进度条
   * @default "false"
   */
  readonly VITE_STARTUP_DEBUG_MODE?: string
  /**
   * 高德地图 JS API Key
   * 申请地址: https://console.amap.com/
   */
  readonly VITE_AMAP_KEY?: string
}

interface ImportMeta {
  readonly env: ImportMetaEnv
}
