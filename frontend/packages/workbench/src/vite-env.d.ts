/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_API_URL?: string
  readonly VITE_EVOCLOUD_MEMBER_BASE_URL?: string
  readonly VITE_DUTY_DEMO?: string
  readonly VITE_STARTUP_DEBUG_MODE?: string
  readonly VITE_AMAP_KEY?: string
}

interface ImportMeta {
  readonly env: ImportMetaEnv
}
