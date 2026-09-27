import {create} from "zustand"

interface HostEntity {
  type: string
  id: string
}

export interface HostContext {
  route: string
  pageName: string
  entity: HostEntity | null
  /** 宿主声明的域（host_declared，预选/装配的最高优先信号） */
  domain: string | null
  ts: number
}

interface HostContextState {
  context: HostContext | null
  connected: boolean
  /** 仅标记运行于宿主 iframe（乐观态：UI 裁剪不等消息，数据由 context 补充） */
  markEmbedded: () => void
  setContext: (ctx: HostContext) => void
  clear: () => void
}

const MAX_ROUTE_LEN = 200
const MAX_PAGE_LEN = 50
const MAX_ID_LEN = 64

function clampStr(v: unknown, max: number): string {
  return typeof v === "string" ? v.slice(0, max) : ""
}

/** 宿主（Member Center 后台）注入的页面上下文，模块级单例 */
export const useHostContextStore = create<HostContextState>((set) => ({
  context: null,
  connected: false,
  markEmbedded: () => set({ connected: true }),
  setContext: (ctx) => set({ context: ctx, connected: true }),
  clear: () => set({ context: null, connected: false }),
}))

export function normalizeHostContext(raw: unknown): HostContext | null {
  if (!raw || typeof raw !== "object") return null
  const p = raw as Record<string, unknown>
  const route = clampStr(p.route, MAX_ROUTE_LEN)
  if (!route) return null
  const entityRaw = p.entity as Record<string, unknown> | null | undefined
  const entity =
    entityRaw && typeof entityRaw === "object" && entityRaw.id
      ? {
          type: clampStr(entityRaw.type, 30) || "unknown",
          id: clampStr(entityRaw.id, MAX_ID_LEN),
        }
      : null
  return {
    route,
    pageName: clampStr(p.page_name ?? p.pageName, MAX_PAGE_LEN),
    entity,
    domain: clampStr(p.domain, 64) || null,
    ts: typeof p.ts === "number" ? p.ts : Date.now(),
  }
}
